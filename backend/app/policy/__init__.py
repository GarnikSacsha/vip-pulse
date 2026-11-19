"""Deterministic policy: facts computed in code, priority decided by explicit rules.

The LLM supplies meaning (category, sentiment, next step). Timing, SLA, safety
overrides and the final priority are computed here, so every decision is
reproducible, testable and explainable with a list of reasons.
"""
