"""Prompt construction. Messages are rendered with their ids so the model can cite them."""

import json
from typing import Any

from app.policy.facts import ConversationFacts
from app.schemas.analysis import LLMAnalysis
from app.schemas.domain import Conversation, Player

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """\
Ты — аналитик качества VIP-отдела онлайн-казино. Разбираешь переписку VIP-менеджера с игроком
и возвращаешь ОДИН JSON-объект строго по схеме. Без текста вне JSON.

Правила:
1. Опирайся только на текст переписки. Не придумывай статусы платежей, суммы, сроки и факты.
   Если данных не хватает — так и напиши в summary и снизь confidence.
2. evidence_message_ids — точные id сообщений из квадратных скобок, на которых основан вывод.
   Если requires_action=true или safety_flag не "none", процитируй хотя бы одно сообщение.
3. requires_action=true, только если менеджеру есть что сделать: ответить на вопрос, решить
   проблему, выполнить обещание. Благодарность игрока в конце закрытого вопроса — не действие.
4. next_action — один конкретный шаг для менеджера, на русском, до 2 предложений.
5. safety_flag="responsible_gaming", если игрок просит самоисключение/лимиты, говорит о потере
   контроля, долгах, отчаянии. safety_flag="fraud_security" — взлом, чужие входы или платежи.
6. Никогда не советуй бонусы, фриспины, кэшбэк или "отыграться" игроку с сигналом
   ответственной игры. Мы помогаем решать вопросы игрока, а не стимулируем игру.
7. Приоритет не выставляй: его считает отдельная политика по твоим полям и времени ответа.
8. summary — 1–3 предложения на русском: суть запроса и его текущее состояние.
"""


def render_conversation(conv: Conversation) -> str:
    lines = []
    for m in conv.messages:
        stamp = m.sent_at.strftime("%Y-%m-%d %H:%M UTC")
        text = " ".join(m.text.split())  # one line per message keeps ids unambiguous
        lines.append(f"[{m.message_id}] {stamp} · {m.sender_role.value}: {text}")
    return "\n".join(lines)


def build_user_prompt(conv: Conversation, player: Player | None, facts: ConversationFacts) -> str:
    profile = "нет данных"
    if player is not None:
        parts = [f"segment={player.segment}" if player.segment else None]
        parts += [f"{k}={v}" for k, v in sorted(player.attributes.items())]
        profile = ", ".join(p for p in parts if p) or "нет данных"
    wait = f"{facts.wait_hours:g} ч" if facts.wait_hours is not None else "никто не ждёт"
    return (
        f"Канал: {conv.channel.value}\n"
        f"Профиль игрока: {profile}\n"
        f"Факты (посчитаны кодом): последнее сообщение от {facts.last_sender.value}; "
        f"ожидание ответа: {wait}\n\n"
        f"Переписка:\n{render_conversation(conv)}\n"
    )


def response_schema() -> dict[str, Any]:
    return LLMAnalysis.model_json_schema()


def schema_fingerprint() -> str:
    return json.dumps(response_schema(), sort_keys=True, ensure_ascii=False)
