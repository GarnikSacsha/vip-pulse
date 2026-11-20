"""Offline, deterministic stand-in for a real LLM.

Used for tests, CI and demos without an API key. It reads the same prompt a
real model gets and answers with simple keyword heuristics, so the whole
pipeline (prompt -> JSON -> validation -> policy) runs end to end. Its results
are labelled `fake:heuristic-v1` everywhere and must not be presented as AI output.
"""

import json
import re
from typing import Any, ClassVar

_LINE = re.compile(r"^\[(?P<id>[^\]]+)\] [^·]+ · (?P<role>player|manager|system): (?P<text>.*)$")

_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("responsible_gaming", ("самоисключ", "не могу остановиться", "заблокируйте меня", "лудоман")),
    ("account", ("пароль", "вход в аккаунт", "взлом", "это был не я", "логин", "password")),
    ("verification", ("верификац", "документ", "паспорт", "kyc", "verify")),
    ("withdrawal", ("вывод", "вывел", "выплат", "withdraw", "payout")),
    ("deposit", ("депозит", "пополн", "deposit")),
    ("technical", ("завис", "вылет", "ошибк", "не грузит", "crash", "error", "bug")),
)
_THANKS = ("спасибо", "благодар", "thank", "всё пришло", "все пришло")
_NEGATIVE = ("нет ответа", "ответа нет", "где мои", "ухожу", "срочно", "не пришло", "сколько можно")
_URGENT = ("срочно", "где мои", "ухожу", "не могу вывести", "это был не я")
_PROMISE = ("вернусь", "отпишусь", "сообщу", "напишу вам")
_STILL_WAITING = ("ответа нет", "нет ответа", "прошли сутки", "сколько можно", "до сих пор")
_ASKS_WHEN = ("когда", "сколько ждать", "какой срок")
_FOLLOW_UP = ("есть новости", "ну что", "и что", "?")
_TIMING = ("сегодня", "завтра", "час", "дн", "минут", "недел")
_RG = ("самоисключ", "не могу остановиться", "заблокируйте меня", "закрыть аккаунт")
_FRAUD = ("это был не я", "это не я", "взлом", "hacked")

_ACTIONS = {
    "withdrawal": "Проверить статус вывода у платёжной команды и сообщить игроку срок зачисления.",
    "deposit": "Проверить зачисление депозита и подтвердить игроку результат.",
    "verification": "Узнать статус проверки документов и сообщить игроку сроки.",
    "account": "Передать в безопасность, проверить входы и помочь игроку защитить аккаунт.",
    "technical": "Уточнить устройство и версию приложения, передать баг в техподдержку.",
    "responsible_gaming": "Передать специалисту по ответственной игре, акций не предлагать.",
    "general": "Ответить игроку по существу последнего сообщения.",
    "other": "Уточнить у игрока, с чем нужна помощь.",
}


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def _manager_errors(human: list[dict[str, str]]) -> list[dict[str, object]]:
    """Two mistakes keywords can spot: a broken promise and a question left without a date."""
    errors: list[dict[str, object]] = []
    for i, m in enumerate(human):
        if m["role"] != "manager":
            continue
        text = m["text"].lower()
        before = [h["text"].lower() for h in human[:i] if h["role"] == "player"]
        after = [h["text"].lower() for h in human[i + 1 :] if h["role"] == "player"]
        if _has(text, _PROMISE) and any(_has(a, _STILL_WAITING) for a in after):
            errors.append({"code": "broken_promise", "evidence_message_ids": [m["id"]]})
        elif (
            before
            and _has(before[-1], _ASKS_WHEN)
            and not _has(text, _TIMING)
            and not any(ch.isdigit() for ch in text)
            and any(_has(a, _FOLLOW_UP) for a in after)
        ):
            errors.append({"code": "incomplete_answer", "evidence_message_ids": [m["id"]]})
    return errors


class FakeProvider:
    name: ClassVar[str] = "fake"
    model: ClassVar[str] = "heuristic-v1"
    simulated: ClassVar[bool] = True

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        messages = [m.groupdict() for line in user.splitlines() if (m := _LINE.match(line))]
        human = [m for m in messages if m["role"] != "system"]
        player = [m for m in human if m["role"] == "player"]
        player_text = " ".join(m["text"].lower() for m in player)

        category, evidence = "general", [m["id"] for m in player[-1:]]
        for name, words in _CATEGORIES:
            hits = [m["id"] for m in player if _has(m["text"].lower(), words)]
            if hits:
                category, evidence = name, hits
                break
        if not player:
            category = "other"

        last = human[-1] if human else None
        last_text = last["text"].lower() if last else ""
        closing = last is not None and last["role"] == "player" and _has(last_text, _THANKS)
        requires_action = last is not None and last["role"] == "player" and not closing
        if len(last_text.strip(" ?!.")) == 0 and requires_action:
            category = "other"  # a bare "?" carries no context

        safety = "none"
        if _has(player_text, _RG):
            safety = "responsible_gaming"
        elif _has(player_text, _FRAUD):
            safety = "fraud_security"
        if safety != "none":
            requires_action = True

        negative = _has(player_text, _NEGATIVE)
        sentiment = "positive" if closing else "negative" if negative else "neutral"
        urgency = (
            "high"
            if _has(player_text, _URGENT) or safety != "none"
            else ("medium" if requires_action else "low")
        )
        quote = (player[-1]["text"] if player else "нет сообщений игрока")[:120]
        result = {
            "category": category,
            "sentiment": sentiment,
            "urgency": urgency,
            "summary": f"[fake] Категория: {category}. Последнее сообщение игрока: «{quote}»",
            "requires_action": requires_action,
            "next_action": _ACTIONS[category] if requires_action else None,
            "needs_escalation": negative and "ухожу" in player_text,
            "safety_flag": safety,
            "evidence_message_ids": evidence if (requires_action or safety != "none") else [],
            "confidence": 0.55,
            "manager_errors": _manager_errors(human),
        }
        return json.dumps(result, ensure_ascii=False)
