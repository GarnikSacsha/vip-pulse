"""Gemini REST provider and the spending meter. No network: every HTTP exchange is scripted."""

import http.client
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from app.analysis.llm import LLMError, get_provider
from app.analysis.llm.base import PermanentLLMError
from app.analysis.llm.budget import BudgetExceeded, Pricing, SpendingMeter
from app.analysis.llm.gemini import GeminiProvider, RequestNotSent, gemini_schema, urllib_transport
from app.analysis.prompts import response_schema
from app.config import Settings

PRICING = Pricing(input_per_million=0.30, output_per_million=2.50)
SCHEMA = response_schema()


class Transport:
    """Scripted HTTP: each queued item is (status, headers, json body) or an exception."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, timeout: float
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests.append({"url": url, "headers": headers, "body": json.loads(body)})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, resp_headers, payload = item
        return status, resp_headers, json.dumps(payload).encode()


def _ok(text: str = '{"a": 1}', prompt: int = 1000, out: int = 200, thoughts: int = 0) -> tuple:
    usage = {
        "promptTokenCount": prompt,
        "candidatesTokenCount": out,
        "totalTokenCount": prompt + out,
    }
    if thoughts:
        usage["thoughtsTokenCount"] = thoughts
    return (
        200,
        {},
        {
            "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": usage,
        },
    )


def _provider(transport: Transport, limit: float = 1.0, **kw: Any) -> GeminiProvider:
    sleeps: list[float] = []
    provider = GeminiProvider(
        api_key="test-key-123",
        model="gemini-2.5-flash",
        meter=SpendingMeter(limit_usd=limit),
        pricing=PRICING,
        transport=transport,
        sleep=sleeps.append,
        **kw,
    )
    provider.sleeps = sleeps  # type: ignore[attr-defined]
    return provider


def test_request_carries_prompt_schema_and_key_in_header_only() -> None:
    transport = Transport(_ok())
    text = _provider(transport).complete_json("SYS", "USER", SCHEMA)
    assert text == '{"a": 1}'
    req = transport.requests[0]
    assert req["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert "test-key-123" not in req["url"]
    assert req["headers"]["x-goog-api-key"] == "test-key-123"
    body = req["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["contents"] == [{"role": "user", "parts": [{"text": "USER"}]}]
    cfg = body["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert cfg["responseJsonSchema"] == gemini_schema(SCHEMA)
    assert cfg["temperature"] == 0
    assert cfg["maxOutputTokens"] == 2048
    assert cfg["thinkingConfig"] == {"thinkingBudget": 0}


def test_schema_is_inlined_without_refs() -> None:
    schema = gemini_schema(SCHEMA)
    dumped = json.dumps(schema)
    assert "$ref" not in dumped
    assert "$defs" not in dumped
    assert schema["properties"]["category"]["enum"][0] == "withdrawal"
    assert schema["additionalProperties"] is False


def test_spend_is_metered_from_reported_usage_including_thoughts() -> None:
    provider = _provider(Transport(_ok(prompt=1_000_000, out=100_000, thoughts=100_000)))
    provider.complete_json("s", "u", SCHEMA)
    # 1M input * 0.30 + 0.2M output (answer + thinking) * 2.50
    assert provider.meter.spent_usd == pytest.approx(0.30 + 0.50)
    [record] = provider.meter.drain()
    assert (record.input_tokens, record.output_tokens) == (1_000_000, 200_000)
    assert record.model == "gemini:gemini-2.5-flash"
    assert record.estimated is False


def test_no_call_is_made_when_the_budget_cannot_cover_the_worst_case() -> None:
    transport = Transport(_ok())
    provider = _provider(transport, limit=0.001)
    with pytest.raises(BudgetExceeded):
        provider.complete_json("s", "u" * 4000, SCHEMA)
    assert transport.requests == []
    assert provider.meter.spent_usd == 0


def test_meter_counts_spend_from_earlier_runs() -> None:
    meter = SpendingMeter(limit_usd=1.0, spent_usd=0.999)
    with pytest.raises(BudgetExceeded):
        meter.reserve(0.01)
    meter.reserve(0.0005)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_errors_are_retried_with_backoff(status: int) -> None:
    transport = Transport((status, {}, {"error": {"message": "busy"}}), _ok())
    provider = _provider(transport)
    assert provider.complete_json("s", "u", SCHEMA) == '{"a": 1}'
    assert len(transport.requests) == 2
    assert provider.sleeps == [1.0]  # type: ignore[attr-defined]
    assert provider.meter.spent_usd > 0  # only the successful call is billed
    assert len(provider.meter.drain()) == 1


def test_retry_after_header_is_respected() -> None:
    transport = Transport((429, {"Retry-After": "7"}, {}), _ok())
    provider = _provider(transport)
    provider.complete_json("s", "u", SCHEMA)
    assert provider.sleeps == [7.0]  # type: ignore[attr-defined]


def test_gives_up_after_max_retries() -> None:
    transport = Transport(*[(503, {}, {})] * 3)
    provider = _provider(transport, max_retries=2)
    with pytest.raises(LLMError, match="HTTP 503"):
        provider.complete_json("s", "u", SCHEMA)
    assert len(transport.requests) == 3
    assert provider.sleeps == [1.0, 2.0]  # type: ignore[attr-defined]


def test_client_errors_are_not_retried_and_do_not_leak_the_key() -> None:
    transport = Transport((400, {}, {"error": {"message": "API key not valid: test-key-123"}}))
    provider = _provider(transport)
    with pytest.raises(LLMError) as exc:
        provider.complete_json("s", "u", SCHEMA)
    assert "HTTP 400" in str(exc.value)
    assert "test-key-123" not in str(exc.value)
    assert len(transport.requests) == 1


def test_network_failure_is_retried_and_charged_conservatively() -> None:
    transport = Transport(TimeoutError("timed out"), _ok())
    provider = _provider(transport)
    provider.complete_json("s", "u", SCHEMA)
    first, second = provider.meter.drain()
    # The lost request may still have been billed: its worst case is booked.
    assert first.estimated is True and first.cost_usd > 0
    assert second.estimated is False


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked"),
        ({"candidates": []}, "no candidates"),
        (
            {"candidates": [{"content": {"parts": [{"text": "{"}]}, "finishReason": "MAX_TOKENS"}]},
            "MAX_TOKENS",
        ),
        ({"candidates": [{"finishReason": "SAFETY"}]}, "SAFETY"),
    ],
)
def test_unusable_answers_fail_closed(payload: dict, error: str) -> None:
    payload["usageMetadata"] = {"promptTokenCount": 10, "candidatesTokenCount": 5}
    provider = _provider(Transport((200, {}, payload)))
    with pytest.raises(LLMError, match=error):
        provider.complete_json("s", "u", SCHEMA)
    assert provider.meter.spent_usd > 0  # the call was billed even though it is unusable


def test_thought_parts_are_not_part_of_the_answer() -> None:
    status, headers, payload = _ok()
    payload["candidates"][0]["content"]["parts"] = [
        {"text": "thinking...", "thought": True},
        {"text": '{"b": 2}'},
    ]
    provider = _provider(Transport((status, headers, payload)))
    assert provider.complete_json("s", "u", SCHEMA) == '{"b": 2}'


def test_gemini_requires_a_key() -> None:
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        get_provider(Settings(llm_provider="gemini", gemini_api_key=None))


def test_gemini_is_built_from_settings_with_budget() -> None:
    provider = get_provider(Settings(llm_provider="gemini", gemini_api_key="k", llm_budget_usd=0.5))
    assert isinstance(provider, GeminiProvider)
    assert provider.simulated is False
    assert provider.meter.limit_usd == 0.5
    # gemini-2.5-flash is closed to new users (HTTP 404, 2026-11-19).
    assert provider.model == "gemini-3.8-flash"
    assert (provider.pricing.input_per_million, provider.pricing.output_per_million) == (0.75, 3.75)


# --- review fixes: reservations, unsent requests, permanent failures ------------------------


def _released(provider: GeminiProvider) -> bool:
    """No reservation is left behind: everything not spent is available again."""
    meter = provider.meter
    return meter.remaining_usd == pytest.approx(meter.limit_usd - meter.spent_usd)


@pytest.mark.parametrize(
    "payload",
    [[1, 2], {"candidates": [{"finishReason": 7}]}, {"candidates": "x"}],
)
def test_malformed_answer_fails_without_leaking_the_reservation(payload: Any) -> None:
    provider = _provider(Transport((200, {}, payload)))
    with pytest.raises(LLMError):
        provider.complete_json("s", "u", SCHEMA)
    assert _released(provider)
    [record] = provider.meter.drain()
    assert record.estimated is True  # the request reached Google: book the worst case


def test_unexpected_transport_error_does_not_leak_the_reservation() -> None:
    provider = _provider(Transport(ValueError("weird")))
    with pytest.raises(LLMError):
        provider.complete_json("s", "u", SCHEMA)
    assert _released(provider)


def test_request_that_was_never_sent_is_not_charged() -> None:
    transport = Transport(RequestNotSent("dns failure"), _ok())
    provider = _provider(transport)
    provider.complete_json("s", "u", SCHEMA)
    [record] = provider.meter.drain()  # only the successful call
    assert record.estimated is False
    assert _released(provider)


def test_offline_costs_nothing() -> None:
    provider = _provider(Transport(*[RequestNotSent("offline")] * 4))
    with pytest.raises(LLMError, match="not sent"):
        provider.complete_json("s", "u", SCHEMA)
    assert provider.meter.spent_usd == 0
    assert provider.meter.drain() == []


@pytest.mark.parametrize(
    "response",
    [
        (200, {}, {"promptFeedback": {"blockReason": "SAFETY"}}),
        (200, {}, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
        (400, {}, {"error": {"message": "bad request"}}),
    ],
)
def test_failures_that_would_repeat_are_permanent(response: tuple) -> None:
    provider = _provider(Transport(response))
    with pytest.raises(PermanentLLMError):
        provider.complete_json("s", "u", SCHEMA)


def test_urllib_transport_tells_unsent_from_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*args: Any, **kwargs: Any) -> Any:
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(urllib.request, "urlopen", refused)
    with pytest.raises(RequestNotSent):
        urllib_transport("https://x.invalid", {}, b"{}", 1.0)

    def cut(*args: Any, **kwargs: Any) -> Any:
        raise http.client.IncompleteRead(b"partial")

    monkeypatch.setattr(urllib.request, "urlopen", cut)
    with pytest.raises(OSError) as exc:
        urllib_transport("https://x.invalid", {}, b"{}", 1.0)
    assert not isinstance(exc.value, RequestNotSent)  # sent, answer lost: may be billed


def test_schema_keeps_a_property_called_title() -> None:
    schema = {
        "type": "object",
        "title": "Model",
        "properties": {"title": {"type": "string", "title": "Title"}},
        "required": ["title"],
    }
    assert gemini_schema(schema) == {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
    }


def test_reset_clears_reservations_and_returns_unsaved_records() -> None:
    meter = SpendingMeter(limit_usd=1.0)
    meter.reserve(0.5)  # left behind by a crashed run
    meter.settle(0.0, model="m", cost_usd=0.1)  # booked but never saved
    leftover = meter.reset_spent(0.3)
    assert [r.cost_usd for r in leftover] == [0.1]
    assert meter.remaining_usd == pytest.approx(0.7)
