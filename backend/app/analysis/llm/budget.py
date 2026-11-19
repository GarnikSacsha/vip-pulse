"""Spending cap for paid providers.

A provider reserves the worst-case cost of a call before sending it and settles the real cost
after. The reservation is what makes the cap hard: with parallel calls, every in-flight request
already counts against the limit, so the total can only overshoot by the gap between the
worst-case estimate and the provider's real token count.
"""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from app.analysis.llm.base import LLMError


class BudgetExceeded(LLMError):
    """The next call could exceed the spending limit, so it was not sent."""


@dataclass(frozen=True)
class Pricing:
    """USD per one million tokens. Thinking tokens are billed as output."""

    input_per_million: float
    output_per_million: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million + output_tokens * self.output_per_million
        ) / 1_000_000


@dataclass(frozen=True)
class CallRecord:
    at: datetime
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    # True when the provider reported no usage (e.g. a lost response): the worst case is booked.
    estimated: bool
    outcome: str  # "ok" or a short error label


class SpendingMeter:
    """Thread-safe running total against a limit, plus the calls not yet persisted."""

    def __init__(self, limit_usd: float, spent_usd: float = 0.0) -> None:
        self.limit_usd = limit_usd
        self._spent = spent_usd
        self._reserved = 0.0
        self._records: list[CallRecord] = []
        self._lock = threading.Lock()

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._spent

    @property
    def remaining_usd(self) -> float:
        with self._lock:
            return max(0.0, self.limit_usd - self._spent - self._reserved)

    def reset_spent(self, spent_usd: float) -> None:
        """Start a run from the persisted total (spend of earlier runs and processes)."""
        with self._lock:
            self._spent = spent_usd

    def reserve(self, max_cost_usd: float) -> None:
        with self._lock:
            if self._spent + self._reserved + max_cost_usd > self.limit_usd:
                raise BudgetExceeded(
                    f"spending limit ${self.limit_usd:.2f} reached "
                    f"(spent ${self._spent:.4f}); call not sent"
                )
            self._reserved += max_cost_usd

    def settle(
        self,
        reserved_usd: float,
        *,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        estimated: bool = False,
        outcome: str = "ok",
        billed: bool = True,
    ) -> None:
        """Release a reservation and book the real cost. Unbilled attempts leave no record."""
        with self._lock:
            self._reserved = max(0.0, self._reserved - reserved_usd)
            if not billed:
                return
            self._spent += cost_usd
            self._records.append(
                CallRecord(
                    at=datetime.now(UTC),
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    estimated=estimated,
                    outcome=outcome,
                )
            )

    def drain(self) -> list[CallRecord]:
        with self._lock:
            records, self._records = self._records, []
            return records


def meter_of(provider: object) -> SpendingMeter | None:
    """The spending meter of a paid provider; None for free stand-ins such as the fake."""
    meter = getattr(provider, "meter", None)
    return meter if isinstance(meter, SpendingMeter) else None
