"""Typed policy configuration loaded from thresholds.yaml."""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.domain import Channel

DEFAULT_POLICY_PATH = Path(__file__).with_name("thresholds.yaml")


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SlaConfig(_Cfg):
    response_hours: float = Field(gt=0)
    critical_wait_hours: float = Field(gt=0)
    channel_response_hours: dict[Channel, float] = Field(default_factory=dict)

    def response_hours_for(self, channel: Channel) -> float:
        return self.channel_response_hours.get(channel, self.response_hours)


class AnalysisConfig(_Cfg):
    min_confidence: float = Field(ge=0, le=1)


class SafetyConfig(_Cfg):
    responsible_gaming: tuple[str, ...]
    fraud_security: tuple[str, ...]

    @field_validator("responsible_gaming", "fraud_security")
    @classmethod
    def _lower(cls, words: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(w.lower() for w in words)


class PlayerConfig(_Cfg):
    # account_status values that forbid offers; "self_excluded" also routes to the RG specialist.
    restricted_statuses: tuple[str, ...] = ("self_excluded", "limit_set")
    failed_deposits_7d: int = Field(default=3, ge=1)
    pending_withdrawal_usd: float = Field(default=1000, gt=0)
    deposit_drop_share: float = Field(default=0.5, gt=0, lt=1)  # now < share × previous 30 days
    deposit_spike_ratio: float = Field(default=1.7, gt=1)  # now > ratio × previous 30 days


class PolicyConfig(_Cfg):
    sla: SlaConfig
    analysis: AnalysisConfig
    safety: SafetyConfig
    offers: tuple[str, ...]
    player: PlayerConfig = PlayerConfig()

    @field_validator("offers")
    @classmethod
    def _lower(cls, words: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(w.lower() for w in words)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "PolicyConfig":
        source = Path(path) if path else DEFAULT_POLICY_PATH
        return cls.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


# "без бонусов", "no bonus today", "не предлагаю бонус": a word right before the offer (or one
# word before it) that negates it. Refusing an offer is not making one.
_NEGATION = re.compile(r"(?:^|\W)(?:без|не|нет|никаких|no|not|without|never)\W+(?:\w+\W+)?$")


def mentions_offer(text: str, words: tuple[str, ...]) -> bool:
    """True when the text offers something from `words`.

    A message that refuses an offer anywhere ("давай сегодня без бонусов") is a refusal as a
    whole, even when it also quotes the player's request ("ты просишь бонусы").
    """
    lowered = text.lower()
    plain = False
    for word in words:
        start = lowered.find(word)
        while start != -1:
            if _NEGATION.search(lowered[max(0, start - 30) : start]):
                return False
            plain = True
            start = lowered.find(word, start + 1)
    return plain
