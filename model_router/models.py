"""Pydantic data models for the registry, task signals, and routing results.

All models are immutable (`frozen=True`) — the router never mutates inputs, it
returns new objects. Keeps reasoning about routing easy and side-effect-free.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Recognised capability tags. Anything else in the registry is rejected at load
# time so typos surface immediately instead of silently never matching.
Capability = Literal[
    "reasoning",
    "coding",
    "vision",
    "tool_use",
    "long_context",
    "cheap_bulk",
]

CAPABILITIES: tuple[str, ...] = (
    "reasoning",
    "coding",
    "vision",
    "tool_use",
    "long_context",
    "cheap_bulk",
)


class Model(BaseModel, frozen=True):
    """A single registry entry describing one model."""

    id: str
    provider: str
    open_weights: bool = False
    context_window: int = Field(gt=0)
    max_output: int | None = Field(default=None, gt=0)
    capabilities: tuple[Capability, ...] = ()
    cost_tier: int = Field(ge=1, le=5)
    speed_tier: int = Field(ge=1, le=5)
    notes: str = ""

    def has(self, capability: str) -> bool:
        return capability in self.capabilities


class TaskSignals(BaseModel, frozen=True):
    """What the task needs. Either inferred from text or set explicitly.

    `needed_capabilities` are hard-ish requirements (heavily weighted).
    The *_sensitive flags and `open_only` shape the trade-offs.
    """

    needed_capabilities: tuple[Capability, ...] = ()
    est_context_tokens: int = 0
    cost_sensitive: bool = False
    latency_sensitive: bool = False
    open_only: bool = False
    max_context: int | None = None  # hard filter: model.context_window must be >=
    source: str = "explicit"  # "inferred" | "explicit" | "merged"

    def needs(self, capability: str) -> bool:
        return capability in self.needed_capabilities


class ScoredModel(BaseModel, frozen=True):
    """A model plus its computed score and a per-signal breakdown."""

    model: Model
    score: float
    breakdown: dict[str, float]
    reasons: tuple[str, ...] = ()


class Recommendation(BaseModel, frozen=True):
    """The full routing result: best pick, ranked alternatives, rationale."""

    signals: TaskSignals
    best: ScoredModel | None
    alternatives: tuple[ScoredModel, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()  # (model_id, reason)
    rationale: str = ""
