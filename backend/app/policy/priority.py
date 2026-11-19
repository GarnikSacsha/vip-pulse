"""Final priority for a conversation, with the reasons that produced it."""

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from app.policy.config import PolicyConfig, contains_any
from app.policy.facts import ConversationFacts
from app.policy.safety import SafetySignal
from app.schemas.analysis import MONEY_CATEGORIES, LLMAnalysis, Priority, SafetyFlag, Urgency

if TYPE_CHECKING:
    from app.policy.player import PlayerSignals

SAFE_RG_ACTION = (
    "Не предлагать бонусы и акции. Подтвердить игроку, что запрос получен, и передать "
    "специалисту по ответственной игре (самоисключение / ограничения)."
)
SAFE_FRAUD_ACTION = (
    "Передать в службу безопасности: проверить входы и платежи, при необходимости "
    "заблокировать сессии. Подтвердить игроку, что запрос в работе."
)
SAFE_RESTRICTED_ACTION = (
    "Не предлагать бонусы и акции: на аккаунте игрока стоят ограничения. Ответить по существу "
    "запроса."
)
FALLBACK_ACTION = (
    "Автоматический разбор недоступен: прочитать переписку вручную и определить следующий шаг."
)
# Shown next to every reason derived from the analysis, so a simulated result is never
# mistaken for model output.
LABEL_MODEL = "AI"
LABEL_SIMULATED = "эвристика fake, без модели"


class Route(StrEnum):
    MANAGER = "manager"
    RG_SPECIALIST = "rg_specialist"
    SECURITY = "security"


class Reason(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    text: str


class PriorityDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    priority: Priority
    route: Route
    reasons: tuple[Reason, ...]
    next_action: str | None
    suppress_offers: bool
    requires_human_review: bool
    quality_flags: tuple[str, ...]


def _max(a: Priority, b: Priority) -> Priority:
    return min(a, b)  # P0 < P1 < ...: the smaller string is the more urgent


def decide(
    facts: ConversationFacts,
    analysis: LLMAnalysis | None,
    safety: SafetySignal,
    cfg: PolicyConfig,
    *,
    simulated: bool,
    player: "PlayerSignals | None" = None,
) -> PriorityDecision:
    source = LABEL_SIMULATED if simulated else LABEL_MODEL
    reasons: list[Reason] = []
    quality: list[str] = []
    priority = Priority.P3
    route = Route.MANAGER
    review = False

    def bump(level: Priority, code: str, text: str) -> None:
        nonlocal priority
        priority = _max(priority, level)
        reasons.append(Reason(code=code, text=text))

    # 1. Safety: keyword net OR the LLM, whichever fires. Never downgraded by later rules.
    flag = safety.flag
    # Keyword hits are facts found by code; a flag that only the analysis raised is labelled.
    suffix = ""
    if flag == SafetyFlag.NONE and analysis is not None:
        flag = analysis.safety_flag
        suffix = f" ({source})"
    if flag == SafetyFlag.RESPONSIBLE_GAMING:
        route, review = Route.RG_SPECIALIST, True
        bump(
            Priority.P0, "safety.responsible_gaming", f"Сигнал ответственной игры у игрока{suffix}"
        )
    elif flag == SafetyFlag.FRAUD_SECURITY:
        route, review = Route.SECURITY, True
        bump(Priority.P0, "safety.fraud_security", f"Возможный взлом или мошенничество{suffix}")
    # 1b. The player's profile: an account restriction is a safety fact, like a keyword hit.
    if player is not None and player.restricted:
        label = {"self_excluded": "самоисключение", "limit_set": "установлен лимит"}.get(
            player.restricted, player.restricted
        )
        review = True
        if player.self_excluded:
            route = Route.RG_SPECIALIST
            bump(Priority.P0, "player.restricted", f"Аккаунт игрока: {label}")
        else:
            reasons.append(Reason(code="player.restricted", text=f"Аккаунт игрока: {label}"))
        if player.offer_message_ids:
            quality.append("offer_to_restricted_player")
            bump(
                Priority.P1,
                "quality.offer_to_restricted_player",
                f"Менеджер предложил бонус игроку с ограничением ({label})",
            )

    offers_after_rg = safety.offer_after_rg_message_ids
    if not offers_after_rg and flag == SafetyFlag.RESPONSIBLE_GAMING and analysis is not None:
        # The signal came from the analysis: check offers after the messages it cites.
        offers_after_rg = safety.offers_after(analysis.evidence_message_ids)
    if offers_after_rg:
        quality.append("offer_to_vulnerable_player")
        reasons.append(
            Reason(
                code="quality.offer_to_vulnerable_player",
                text="Менеджер предложил бонус игроку с сигналом ответственной игры",
            )
        )

    # 2. Timing: computed in code, independent of the LLM.
    if facts.awaiting_reply and analysis is not None and not analysis.requires_action:
        # e.g. "спасибо, всё пришло": the player spoke last, but there is nothing to answer.
        reasons.append(
            Reason(
                code="sla.no_reply_needed",
                text=f"Игрок написал последним, но ответа не требуется ({source})",
            )
        )
    elif facts.awaiting_reply:
        wait = facts.wait_hours or 0.0
        money = analysis is not None and analysis.category in MONEY_CATEGORIES
        critical = cfg.sla.critical_wait_hours
        if money and wait > critical:
            bump(
                Priority.P0,
                "sla.money_critical",
                f"Финансовый запрос без ответа {wait:.0f} ч (порог {critical:g} ч)",
            )
        elif facts.sla_breached:
            bump(
                Priority.P1,
                "sla.breached",
                f"Игрок ждёт ответа {wait:.0f} ч (SLA {facts.response_sla_hours:g} ч)",
            )
        else:
            bump(Priority.P2, "sla.awaiting_reply", "Последнее сообщение от игрока, ответа нет")

    # 2b. Money problems and trends from the profile (code, not the model).
    if player is not None:
        for reason in player.money_reasons:
            bump(Priority.P1 if facts.awaiting_reply else Priority.P2, reason.code, reason.text)
        for reason in player.trend_reasons:
            bump(Priority.P2, reason.code, reason.text)
        review = review or player.needs_review

    # 3. Meaning from the LLM, or a conservative fallback when it is unavailable.
    if analysis is None:
        review = True
        reasons.append(
            Reason(code="analysis.unavailable", text="Автоматический разбор не выполнен")
        )
        next_action = FALLBACK_ACTION
    else:
        if analysis.needs_escalation:
            bump(Priority.P1, "analysis.escalation", f"Рекомендована эскалация ({source})")
        elif analysis.requires_action and analysis.urgency == Urgency.HIGH:
            bump(Priority.P1, "analysis.high_urgency", f"Срочный запрос ({source})")
        elif analysis.requires_action:
            bump(Priority.P2, "analysis.requires_action", f"Нужно действие менеджера ({source})")
        if analysis.confidence < cfg.analysis.min_confidence:
            review = True
            reasons.append(
                Reason(
                    code="analysis.low_confidence",
                    text=f"Низкая уверенность анализа: {analysis.confidence:.2f} ({source})",
                )
            )
        next_action = analysis.next_action

    # 4. Guardrails on the suggested next step.
    rg = route == Route.RG_SPECIALIST
    restricted = player is not None and player.restricted is not None
    suppress_offers = rg or restricted
    offer_advice = next_action is not None and contains_any(next_action, cfg.offers)
    if suppress_offers and (offer_advice or (rg and next_action is None)):
        if next_action is not None:
            reasons.append(
                Reason(
                    code="guard.offer_removed",
                    text="Совет упоминал бонусы и заменён безопасным шаблоном",
                )
            )
        next_action = SAFE_RG_ACTION if rg else SAFE_RESTRICTED_ACTION
    elif route == Route.SECURITY and next_action is None:
        next_action = SAFE_FRAUD_ACTION

    if not reasons:
        reasons.append(Reason(code="none", text="Открытых запросов нет"))

    return PriorityDecision(
        priority=priority,
        route=route,
        reasons=tuple(reasons),
        next_action=next_action,
        suppress_offers=suppress_offers,
        requires_human_review=review,
        quality_flags=tuple(quality),
    )
