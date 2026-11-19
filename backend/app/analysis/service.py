"""Analyse one conversation. Always returns an AnalysisOutcome; never raises.

Invalid JSON, schema violations and evidence pointing at messages that do not
exist in the conversation are all treated as failures (fail closed): a
hallucinated reason never reaches the manager as if it were a fact.
"""

import hashlib
import json
import re

from pydantic import ValidationError

from app.analysis.llm.base import LLMError, LLMProvider
from app.analysis.llm.budget import BudgetExceeded
from app.analysis.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
    response_schema,
    schema_fingerprint,
)
from app.policy.facts import ConversationFacts
from app.schemas.analysis import AnalysisOutcome, LLMAnalysis, ProcessingStatus
from app.schemas.domain import Conversation, Player

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class InvalidOutput(ValueError):
    pass


def input_hash(provider: LLMProvider, system: str, user: str) -> str:
    """Stable cache key: same model + prompt + schema => same analysis."""
    payload = "\x1f".join(
        [provider.name, provider.model, PROMPT_VERSION, schema_fingerprint(), system, user]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def analysis_key(
    provider: LLMProvider, conv: Conversation, player: Player | None, facts: ConversationFacts
) -> str:
    """Cache key of the analysis this provider would produce for this conversation."""
    return input_hash(provider, SYSTEM_PROMPT, build_user_prompt(conv, player, facts))


def parse_output(raw: str, conv: Conversation) -> LLMAnalysis:
    text = raw.strip()
    if match := _FENCE.match(text):
        text = match.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidOutput(f"model returned invalid JSON: {exc.msg}") from exc
    try:
        result = LLMAnalysis.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "root"
        raise InvalidOutput(f"schema violation at {where}: {first['msg']}") from exc
    unknown = [i for i in result.evidence_message_ids if i not in conv.message_ids]
    if unknown:
        raise InvalidOutput(f"evidence cites messages not in this conversation: {unknown}")
    return result


def analyze_conversation(
    provider: LLMProvider,
    conv: Conversation,
    player: Player | None,
    facts: ConversationFacts,
    max_attempts: int = 2,
) -> AnalysisOutcome:
    user = build_user_prompt(conv, player, facts)
    key = analysis_key(provider, conv, player, facts)
    error = "not attempted"
    for _ in range(max(1, max_attempts)):
        try:
            raw = provider.complete_json(SYSTEM_PROMPT, user, response_schema())
            result = parse_output(raw, conv)
        except BudgetExceeded as exc:  # retrying cannot help; the call was never sent
            error = f"{type(exc).__name__}: {exc}"
            break
        except (LLMError, InvalidOutput) as exc:
            error = f"{type(exc).__name__}: {exc}"
            continue
        except Exception as exc:  # a provider bug must not abort a whole batch
            error = f"unexpected {type(exc).__name__}: {exc}"
            break
        return AnalysisOutcome(
            conversation_id=conv.conversation_id,
            status=ProcessingStatus.OK,
            result=result,
            model=f"{provider.name}:{provider.model}",
            simulated=provider.simulated,
            input_hash=key,
        )
    return AnalysisOutcome(
        conversation_id=conv.conversation_id,
        status=ProcessingStatus.FAILED,
        error=error,
        model=f"{provider.name}:{provider.model}",
        simulated=provider.simulated,
        input_hash=key,
    )
