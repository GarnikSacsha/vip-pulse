"""Gemini over its REST API (`generateContent`), using only the standard library.

Every attempt is reserved against the spending meter first, so no request is sent that could
break the limit. Transient errors (429, 5xx, network) are retried with backoff; anything the
pipeline cannot trust (blocked prompt, truncated or filtered answer) fails closed as LLMError.
"""

import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from app.analysis.llm.base import LLMError
from app.analysis.llm.budget import Pricing, SpendingMeter

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_S = 30.0
# Conservative token estimate for the reservation: Cyrillic text is rarely under 2 chars/token.
CHARS_PER_TOKEN = 2

Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, Mapping[str, str], bytes]]


def urllib_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float
) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic JSON schema with `$ref`s inlined and titles dropped (smaller, no references)."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {k: walk(v) for k, v in node.items() if k not in {"$defs", "title"}}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


class GeminiProvider:
    name = "gemini"
    simulated = False

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        meter: SpendingMeter,
        pricing: Pricing,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        max_output_tokens: int = 2048,
        thinking_budget: int = 0,
        max_retries: int = 3,
        timeout_s: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.meter = meter
        self.pricing = pricing
        self._transport = transport
        self._sleep = sleep
        self.max_output_tokens = max_output_tokens
        self.thinking_budget = thinking_budget
        self.max_retries = max_retries
        self.timeout_s = timeout_s

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}"

    def _redact(self, text: str) -> str:
        return text.replace(self._api_key, "***") if self._api_key else text

    def _worst_case(self, prompt_chars: int) -> float:
        input_tokens = math.ceil(prompt_chars / CHARS_PER_TOKEN)
        return self.pricing.cost(input_tokens, self.max_output_tokens + self.thinking_budget)

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        response_schema = gemini_schema(schema)
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema,
                "temperature": 0,
                "maxOutputTokens": self.max_output_tokens,
                "thinkingConfig": {"thinkingBudget": self.thinking_budget},
            },
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        url = f"{API_BASE}/models/{self.model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}
        worst = self._worst_case(len(system) + len(user) + len(json.dumps(response_schema)))

        last_error, backoff = "no attempt", 0.0
        for attempt in range(self.max_retries + 1):
            if attempt:
                self._sleep(backoff)
            self.meter.reserve(worst)
            try:
                status, resp_headers, raw = self._transport(url, headers, payload, self.timeout_s)
            except OSError as exc:  # timeout, DNS, reset: the request may still have been billed
                self.meter.settle(
                    worst, model=self.label, cost_usd=worst, estimated=True, outcome="network_error"
                )
                last_error = f"Gemini network error: {type(exc).__name__}"
                backoff = float(2**attempt)
                continue

            if status != 200:
                self.meter.settle(worst, model=self.label, billed=False)
                last_error = f"Gemini HTTP {status}: {self._error_message(raw)}"
                if status not in RETRYABLE:
                    raise LLMError(last_error)
                backoff = self._retry_after(resp_headers, attempt)
                continue

            return self._read_answer(raw, worst)
        raise LLMError(last_error)

    @staticmethod
    def _retry_after(headers: Mapping[str, str], attempt: int) -> float:
        value = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
        try:
            seconds = float(value) if value is not None else float(2**attempt)
        except ValueError:
            seconds = float(2**attempt)
        return min(MAX_BACKOFF_S, max(0.0, seconds))

    def _error_message(self, raw: bytes) -> str:
        try:
            message = json.loads(raw)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = "no details"
        return self._redact(str(message))[:200]

    def _read_answer(self, raw: bytes, worst: float) -> str:
        try:
            data = json.loads(raw)
        except ValueError:
            self.meter.settle(
                worst, model=self.label, cost_usd=worst, estimated=True, outcome="bad_response"
            )
            raise LLMError("Gemini returned a non-JSON response") from None

        usage = data.get("usageMetadata") or {}
        if "promptTokenCount" in usage:
            input_tokens = int(usage.get("promptTokenCount", 0))
            output_tokens = int(usage.get("candidatesTokenCount", 0)) + int(
                usage.get("thoughtsTokenCount", 0)
            )
            cost, estimated = self.pricing.cost(input_tokens, output_tokens), False
        else:
            input_tokens = output_tokens = 0
            cost, estimated = worst, True

        def book(outcome: str) -> None:
            self.meter.settle(
                worst,
                model=self.label,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                estimated=estimated,
                outcome=outcome,
            )

        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            book("blocked")
            raise LLMError(f"Gemini blocked the prompt: {block}")
        candidates = data.get("candidates") or []
        if not candidates:
            book("empty")
            raise LLMError("Gemini returned no candidates")
        candidate = candidates[0]
        finish = candidate.get("finishReason", "STOP")
        if finish != "STOP":
            book(f"finish_{finish.lower()}")
            raise LLMError(f"Gemini stopped with {finish}; answer discarded")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        book("ok")
        return text
