"""Heuristic inference of task signals from a free-text task description.

This is intentionally simple, transparent keyword matching — not an LLM call.
The router stays offline and deterministic. Explicit flags (from the CLI or API)
always override inferred values via `merge`.
"""

from __future__ import annotations

import re

from model_router.models import TaskSignals

# Rough average characters per token for English text. Used only to turn a
# pasted blob of context into a coarse token estimate. Edit if your inputs skew.
CHARS_PER_TOKEN = 4

# capability -> keywords that suggest it. Lowercased substring / word matching.
_CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "reasoning": (
        "reason", "reasoning", "think through", "prove", "proof", "analyze",
        "analysis", "architect", "design a system", "plan", "strategy",
        "debug a complex", "root cause", "math", "logic", "step by step",
    ),
    "coding": (
        "code", "coding", "function", "refactor", "implement", "bug", "unit test",
        "compile", "api", "script", "program", "repository", "repo", "stack trace",
        "typescript", "python", "rust", "golang", "java",
    ),
    "vision": (
        "image", "screenshot", "photo", "picture", "diagram", "chart",
        "ocr", "vision", "look at this", "ui mockup",
    ),
    "tool_use": (
        "tool", "function call", "agent", "agentic", "mcp", "call an api",
        "use tools", "orchestrat",
    ),
    "long_context": (
        "long document", "entire codebase", "whole repo", "large context",
        "many files", "book", "transcript", "huge",
    ),
    "cheap_bulk": (
        "bulk", "batch", "thousands of", "classify", "classification",
        "high volume", "tag each", "label each", "for each row",
    ),
}

_COST_KEYWORDS = (
    "cheap", "cheapest", "low cost", "low-cost", "save money", "budget",
    "inexpensive", "cost sensitive", "cost-sensitive", "minimize cost",
)

_LATENCY_KEYWORDS = (
    "fast", "fastest", "low latency", "low-latency", "real time", "real-time",
    "interactive", "quick", "instant", "responsive", "snappy",
)

_OPEN_KEYWORDS = (
    "open source", "open-source", "open weights", "open-weight", "self host",
    "self-host", "self hosted", "self-hosted", "on prem", "on-prem", "local model",
    "run locally", "air gapped", "air-gapped",
)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _estimate_context_tokens(text: str) -> int:
    """Pull an explicit token count out of the text if present; else estimate
    from the length of the description itself (a weak proxy)."""
    # Look for explicit mentions like "200k tokens", "32000 token", "1M context"
    match = re.search(
        r"(\d[\d,\.]*)\s*([km])?\s*(?:token|context|window)", text, re.IGNORECASE
    )
    if match:
        number = float(match.group(1).replace(",", ""))
        suffix = (match.group(2) or "").lower()
        multiplier = {"k": 1_000, "m": 1_000_000}.get(suffix, 1)
        return int(number * multiplier)
    return len(text) // CHARS_PER_TOKEN


def infer_signals(description: str) -> TaskSignals:
    """Infer a `TaskSignals` from a free-text task description via keywords."""
    text = description.lower()

    needed = tuple(
        capability
        for capability, keywords in _CAPABILITY_KEYWORDS.items()
        if _contains_any(text, keywords)
    )

    est_context = _estimate_context_tokens(text)
    # If the user explicitly talks about lots of context, ensure long_context is on.
    if est_context >= 200_000 and "long_context" not in needed:
        needed = needed + ("long_context",)

    return TaskSignals(
        needed_capabilities=needed,
        est_context_tokens=est_context,
        cost_sensitive=_contains_any(text, _COST_KEYWORDS),
        latency_sensitive=_contains_any(text, _LATENCY_KEYWORDS),
        open_only=_contains_any(text, _OPEN_KEYWORDS),
        source="inferred",
    )


def merge(inferred: TaskSignals, overrides: TaskSignals) -> TaskSignals:
    """Layer explicit overrides on top of inferred signals.

    Override semantics:
      * needed_capabilities  -> union (explicit flags add to, never erase, inference)
      * boolean flags        -> OR (an explicit True wins; False leaves inference)
      * max_context          -> explicit wins when set
      * est_context_tokens   -> explicit wins when > 0
    """
    return TaskSignals(
        needed_capabilities=tuple(
            dict.fromkeys((*inferred.needed_capabilities, *overrides.needed_capabilities))
        ),
        est_context_tokens=(
            overrides.est_context_tokens
            if overrides.est_context_tokens > 0
            else inferred.est_context_tokens
        ),
        cost_sensitive=inferred.cost_sensitive or overrides.cost_sensitive,
        latency_sensitive=inferred.latency_sensitive or overrides.latency_sensitive,
        open_only=inferred.open_only or overrides.open_only,
        max_context=(
            overrides.max_context
            if overrides.max_context is not None
            else inferred.max_context
        ),
        source="merged",
    )
