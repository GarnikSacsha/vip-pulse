"""Keyword safety net that works even when the LLM is unavailable or misses a signal."""

from pydantic import BaseModel, ConfigDict

from app.policy.config import PolicyConfig, contains_any, mentions_offer, mentions_phrase
from app.schemas.analysis import SafetyFlag
from app.schemas.domain import Conversation, SenderRole


class SafetySignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    flag: SafetyFlag = SafetyFlag.NONE
    message_ids: tuple[str, ...] = ()
    # Manager offered a bonus after the player raised a responsible-gaming signal.
    offer_after_rg_message_ids: tuple[str, ...] = ()
    # Every manager offer and every message id in conversation order: lets the policy check
    # offers after a signal that only the analysis found.
    manager_offer_ids: tuple[str, ...] = ()
    message_order: tuple[str, ...] = ()
    player_message_ids: tuple[str, ...] = ()
    # Player messages about another account or a shared card.
    multi_account_message_ids: tuple[str, ...] = ()

    def offers_after(self, message_ids: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        """Manager offers sent after the earliest of `message_ids`."""
        position = {mid: i for i, mid in enumerate(self.message_order)}
        cited = [position[m] for m in message_ids if m in position]
        if not cited:
            return ()
        first = min(cited)
        return tuple(m for m in self.manager_offer_ids if position.get(m, -1) > first)


def credit_before_security_check(
    conv: Conversation, cfg: PolicyConfig, route: str
) -> tuple[str, ...]:
    """Manager messages crediting or promising a bonus in a security case (decision 0021).

    Only for conversations routed to security. The anchor is the first player message with a
    fraud or shared-account signal (or the first player message when only the analysis saw
    it); a credit after it, before any security check, is a manager mistake. Uses the same
    offer detection as «Бонус уязвимому игроку», refusals included.
    """
    if route != "security":
        return ()

    def credits(text: str) -> bool:
        # Offer words with the offer rules; crediting verbs unless denied right before («не»).
        return mentions_offer(text, cfg.offers) or mentions_phrase(text, cfg.safety.credit_words)

    anchored = False
    found: list[str] = []
    for message in conv.messages:
        if message.sender_role == SenderRole.PLAYER and not anchored:
            text = message.text
            anchored = contains_any(text, cfg.safety.fraud_security) or mentions_phrase(
                text, cfg.safety.multi_account
            )
        elif message.sender_role == SenderRole.MANAGER and anchored and credits(message.text):
            found.append(message.message_id)
    if found or anchored:
        return tuple(found)
    # The analysis alone saw the risk: anchor on the first player message.
    first = next((m for m in conv.messages if m.sender_role == SenderRole.PLAYER), None)
    if first is None:
        return ()
    after = conv.messages[conv.messages.index(first) + 1 :]
    return tuple(
        m.message_id for m in after if m.sender_role == SenderRole.MANAGER and credits(m.text)
    )


def detect_safety(conv: Conversation, cfg: PolicyConfig) -> SafetySignal:
    rg_ids: list[str] = []
    fraud_ids: list[str] = []
    offer_ids: list[str] = []
    manager_offers: list[str] = []
    multi: list[str] = []
    for message in conv.messages:
        if message.sender_role == SenderRole.PLAYER:
            if mentions_phrase(message.text, cfg.safety.multi_account):
                multi.append(message.message_id)
            if contains_any(message.text, cfg.safety.responsible_gaming):
                rg_ids.append(message.message_id)
            if contains_any(message.text, cfg.safety.fraud_security):
                fraud_ids.append(message.message_id)
        elif message.sender_role == SenderRole.MANAGER and mentions_offer(message.text, cfg.offers):
            manager_offers.append(message.message_id)
            if rg_ids:
                offer_ids.append(message.message_id)

    order = tuple(m.message_id for m in conv.messages)
    players = tuple(m.message_id for m in conv.messages if m.sender_role == SenderRole.PLAYER)
    context = {
        "manager_offer_ids": tuple(manager_offers),
        "message_order": order,
        "player_message_ids": players,
        "multi_account_message_ids": tuple(multi),
    }

    # Responsible gaming outranks fraud: it changes what the manager may say at all.
    if rg_ids:
        return SafetySignal(
            flag=SafetyFlag.RESPONSIBLE_GAMING,
            message_ids=tuple(rg_ids),
            offer_after_rg_message_ids=tuple(offer_ids),
            **context,
        )
    if fraud_ids:
        return SafetySignal(flag=SafetyFlag.FRAUD_SECURITY, message_ids=tuple(fraud_ids), **context)
    return SafetySignal(**context)
