"""End-to-end triage of a set of conversations: facts -> analysis -> policy -> sorted queue.

Synchronous and sequential for now; batching, caching and persistence of
analyses arrive in stage 2. Reused by the CLI today and by the API later.
"""

from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.analysis.llm.base import LLMProvider
from app.analysis.service import analyze_conversation
from app.policy.config import PolicyConfig
from app.policy.facts import ConversationFacts, compute_facts, dataset_as_of
from app.policy.priority import PriorityDecision, decide
from app.policy.safety import detect_safety
from app.schemas.analysis import AnalysisOutcome
from app.schemas.domain import Conversation, Player


class TriageItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation: Conversation
    player: Player | None
    facts: ConversationFacts
    analysis: AnalysisOutcome
    decision: PriorityDecision


def triage(
    conversations: Iterable[Conversation],
    players: Iterable[Player],
    provider: LLMProvider,
    cfg: PolicyConfig,
    as_of: datetime | None = None,
) -> list[TriageItem]:
    convs = list(conversations)
    if not convs:
        return []
    by_id = {p.player_id: p for p in players}
    as_of = as_of or dataset_as_of(convs)

    items = []
    for conv in convs:
        player = by_id.get(conv.player_id)
        facts = compute_facts(conv, as_of, cfg.sla)
        outcome = analyze_conversation(provider, conv, player, facts)
        decision = decide(facts, outcome.result, detect_safety(conv, cfg), cfg)
        items.append(
            TriageItem(
                conversation=conv, player=player, facts=facts, analysis=outcome, decision=decision
            )
        )
    # Most urgent first; within a priority, the longest wait first.
    items.sort(key=lambda i: (i.decision.priority, -(i.facts.wait_hours or 0.0)))
    return items
