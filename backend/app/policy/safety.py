"""Keyword safety net that works even when the LLM is unavailable or misses a signal."""

from pydantic import BaseModel, ConfigDict

from app.policy.config import PolicyConfig, contains_any
from app.schemas.analysis import SafetyFlag
from app.schemas.domain import Conversation, SenderRole


class SafetySignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    flag: SafetyFlag = SafetyFlag.NONE
    message_ids: tuple[str, ...] = ()
    # Manager offered a bonus after the player raised a responsible-gaming signal.
    offer_after_rg_message_ids: tuple[str, ...] = ()


def detect_safety(conv: Conversation, cfg: PolicyConfig) -> SafetySignal:
    rg_ids: list[str] = []
    fraud_ids: list[str] = []
    offer_ids: list[str] = []
    for message in conv.messages:
        if message.sender_role == SenderRole.PLAYER:
            if contains_any(message.text, cfg.safety.responsible_gaming):
                rg_ids.append(message.message_id)
            if contains_any(message.text, cfg.safety.fraud_security):
                fraud_ids.append(message.message_id)
        elif (
            message.sender_role == SenderRole.MANAGER
            and rg_ids
            and contains_any(message.text, cfg.offers)
        ):
            offer_ids.append(message.message_id)

    # Responsible gaming outranks fraud: it changes what the manager may say at all.
    if rg_ids:
        return SafetySignal(
            flag=SafetyFlag.RESPONSIBLE_GAMING,
            message_ids=tuple(rg_ids),
            offer_after_rg_message_ids=tuple(offer_ids),
        )
    if fraud_ids:
        return SafetySignal(flag=SafetyFlag.FRAUD_SECURITY, message_ids=tuple(fraud_ids))
    return SafetySignal()
