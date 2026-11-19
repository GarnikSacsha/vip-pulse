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
    # Share of the SLA after which a waiting player counts as "at risk" (lane «Скоро нарушится»).
    at_risk_share: float = Field(default=0.75, gt=0, lt=1)

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


# A refusal right before the offer word ("без бонусов", "no bonus this time", "никаких
# кэшбэков") or a retold request ("ты просил бонус", "you asked for a bonus") is not an offer.
# Other negations ("не пропустите бонус", "нет, бонус уже на счёте") do not refuse anything.
_REFUSAL = re.compile(r"(?:^|\W)(?:без|никаких|no|without)\W+(?:\w+\W+)?$")
_RETOLD = re.compile(
    r"(?:^|\W)(?:просишь|просил|просила|просили|просите|ask|asked|asking)\W+(?:\w+\W+)?$"
)


def mentions_offer(text: str, words: tuple[str, ...]) -> bool:
    """True when some mention of `words` in the text is an offer, not a refusal or a retold ask."""
    lowered = text.lower()
    for word in words:
        start = lowered.find(word)
        while start != -1:
            before = lowered[max(0, start - 30) : start]
            if not _REFUSAL.search(before) and not _RETOLD.search(before):
                return True
            start = lowered.find(word, start + 1)
    return False
