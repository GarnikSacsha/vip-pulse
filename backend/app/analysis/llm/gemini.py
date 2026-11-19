"""Gemini over its REST API (`generateContent`), using only the standard library.

Every attempt is reserved against the spending meter first, so no request is sent that could
break the limit, and every reservation is settled exactly once, whatever happens. Transient
errors (429, 5xx, network) are retried with backoff. Answers the pipeline cannot trust (blocked
prompt, truncated or filtered answer) fail closed as PermanentLLMError: retrying the same prompt
at temperature 0 would only pay for the same failure again.
"""

import http.client
import json
import math
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from app.analysis.llm.base import LLMError, PermanentLLMError
from app.analysis.llm.budget import Pricing, SpendingMeter

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_S = 30.0
# Conservative token estimate for the reservation: Cyrillic text is rarely under 2 chars/token.
CHARS_PER_TOKEN = 2

Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, Mapping[str, str], bytes]]


class RequestNotSent(OSError):
    """The request never reached the server (DNS, refused connection): nothing was billed."""


def urllib_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float
) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except urllib.error.URLError as exc:
        # urllib wraps only failures while connecting and sending the request in URLError;
        # a failure while reading the response surfaces as a plain OSError.
        raise RequestNotSent(str(exc.reason)) from exc
    except http.client.HTTPException as exc:  # e.g. IncompleteRead: sent, answer lost
        raise ConnectionError(type(exc).__name__) from exc


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic JSON schema with `$ref`s inlined and `title` annotations dropped.

    Keys of a `properties` mapping are field names, not annotations, and are always kept.
    """
    defs = schema.get("$defs", {})

    def walk(node: Any, field_names: bool = False) -> Any:
        if isinstance(node, dict):
            if field_names:
                return {k: walk(v) for k, v in node.items()}
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {
                k: walk(v, field_names=(k == "properties"))
                for k, v in node.items()
                if k not in {"$defs", "title"}
            }
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


class _Attempt:
    """One reserved attempt. Settles its reservation exactly once."""

    def __init__(self, meter: SpendingMeter, label: str, worst: float) -> None:
        self.meter, self.label, self.worst = meter, label, worst
        self.settled = False
        meter.reserve(worst)

    def book(self, **kwargs: Any) -> None:
        if not self.settled:
            self.settled = True
            self.meter.settle(self.worst, model=self.label, **kwargs)

    def book_worst_case(self, outcome: str) -> None:
        self.book(cost_usd=self.worst, estimated=True, outcome=outcome)


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
        for attempt_no in range(self.max_retries + 1):
            if attempt_no:
                self._sleep(backoff)
            attempt = _Attempt(self.meter, self.label, worst)
            try:
                status, resp_headers, raw = self._transport(url, headers, payload, self.timeout_s)
            except RequestNotSent:
                attempt.book(billed=False)
                last_error = "Gemini request not sent (network unavailable)"
                backoff = float(2**attempt_no)
                continue
            except OSError as exc:  # timeout or reset after sending: it may have been billed
                attempt.book_worst_case("network_error")
                last_error = f"Gemini network error: {type(exc).__name__}"
                backoff = float(2**attempt_no)
                continue
            except Exception as exc:
                attempt.book_worst_case("transport_error")
                raise LLMError(f"Gemini transport failed: {type(exc).__name__}") from None

            if status != 200:
                attempt.book(billed=False)
                last_error = f"Gemini HTTP {status}: {self._error_message(raw)}"
                if status not in RETRYABLE:
                    raise PermanentLLMError(last_error)
                backoff = self._retry_after(resp_headers, attempt_no)
                continue

            try:
                return self._read_answer(raw, attempt)
            except LLMError:
                raise
            except Exception as exc:  # malformed body: never crash, never leak the reservation
                raise LLMError(
                    f"Gemini returned a malformed response: {type(exc).__name__}"
                ) from None
            finally:
                attempt.book_worst_case("bad_response")  # no-op when already booked
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

    def _read_answer(self, raw: bytes, attempt: _Attempt) -> str:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise LLMError("Gemini response is not a JSON object")

        usage = data.get("usageMetadata") or {}
        if "promptTokenCount" in usage:
            input_tokens = int(usage.get("promptTokenCount", 0))
            output_tokens = int(usage.get("candidatesTokenCount", 0)) + int(
                usage.get("thoughtsTokenCount", 0)
            )
            cost, estimated = self.pricing.cost(input_tokens, output_tokens), False
        else:
            input_tokens = output_tokens = 0
            cost, estimated = attempt.worst, True

        def book(outcome: str) -> None:
            attempt.book(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                estimated=estimated,
                outcome=outcome,
            )

        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            book("blocked")
            raise PermanentLLMError(f"Gemini blocked the prompt: {block}")
        candidates = data.get("candidates") or []
        if not candidates:
            book("empty")
            raise PermanentLLMError("Gemini returned no candidates")
        candidate = candidates[0]
        finish = str(candidate.get("finishReason", "STOP"))
        if finish != "STOP":
            book(f"finish_{finish.lower()}"[:32])
            raise PermanentLLMError(f"Gemini stopped with {finish}; answer discarded")
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought"))
        book("ok")
        return text
