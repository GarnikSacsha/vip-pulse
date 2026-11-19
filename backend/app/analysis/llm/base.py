"""Provider contract."""

from typing import Any, Protocol


class LLMError(Exception):
    """Provider-level failure (network, quota, refusal). The caller records it, never crashes."""


class LLMProvider(Protocol):
    name: str
    model: str
    # True for stand-ins that do not call a model; their output must never be shown as AI.
    simulated: bool

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        """Return the raw model text, expected to be one JSON object matching `schema`."""
        ...
