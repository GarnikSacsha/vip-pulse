"""Typed policy configuration loaded from thresholds.yaml."""

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


class PolicyConfig(_Cfg):
    sla: SlaConfig
    analysis: AnalysisConfig
    safety: SafetyConfig
    offers: tuple[str, ...]

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
