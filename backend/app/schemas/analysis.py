"""Taxonomy and the structured result an LLM must return for one conversation.

The LLM describes *meaning* (category, sentiment, next step, evidence).
It never sets the final priority: that is decided by the deterministic policy
in `app.policy`, which can be explained and tuned without re-prompting.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Category(StrEnum):
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    VERIFICATION = "verification"
    ACCOUNT = "account"
    TECHNICAL = "technical"
    GENERAL = "general"
    RESPONSIBLE_GAMING = "responsible_gaming"
    OTHER = "other"


MONEY_CATEGORIES = frozenset({Category.WITHDRAWAL, Category.DEPOSIT, Category.VERIFICATION})


class Priority(StrEnum):
    """P0 is the most urgent. String values sort in urgency order."""

    P0 = "P0"  # critical: act now / specialist review
    P1 = "P1"  # high: today
    P2 = "P2"  # medium: needs action, not urgent
    P3 = "P3"  # low: informational, nothing pending


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class Urgency(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SafetyFlag(StrEnum):
    NONE = "none"
    RESPONSIBLE_GAMING = "responsible_gaming"  # self-exclusion, distress, compulsive play
    FRAUD_SECURITY = "fraud_security"  # account takeover, suspicious payments


class ProcessingStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class LLMAnalysis(BaseModel):
    """Exact JSON contract the LLM must produce. Unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Category
    sentiment: Sentiment
    urgency: Urgency
    summary: str = Field(min_length=1, max_length=600)
    requires_action: bool
    next_action: str | None = Field(default=None, max_length=400)
    needs_escalation: bool = False
    safety_flag: SafetyFlag = SafetyFlag.NONE
    evidence_message_ids: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence_message_ids")
    @classmethod
    def _dedupe(cls, ids: list[str]) -> list[str]:
        return list(dict.fromkeys(i.strip() for i in ids if i.strip()))

    @model_validator(mode="after")
    def _consistency(self) -> "LLMAnalysis":
        if self.requires_action and not self.next_action:
            raise ValueError("next_action is required when requires_action is true")
        needs_evidence = self.requires_action or self.safety_flag != SafetyFlag.NONE
        if needs_evidence and not self.evidence_message_ids:
            raise ValueError("evidence_message_ids must cite at least one message")
        return self


class AnalysisOutcome(BaseModel):
    """Result of analysing one conversation, successful or not. Never raises upward."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    status: ProcessingStatus
    result: LLMAnalysis | None = None
    error: str | None = None
    model: str | None = None
    input_hash: str | None = None

    @model_validator(mode="after")
    def _status_matches_payload(self) -> "AnalysisOutcome":
        if self.status == ProcessingStatus.OK and self.result is None:
            raise ValueError("ok outcome must carry a result")
        if self.status == ProcessingStatus.FAILED and not self.error:
            raise ValueError("failed outcome must carry an error")
        return self
