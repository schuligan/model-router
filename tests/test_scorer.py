"""Scoring + selection tests. These assert the router picks sensible models for
crafted task signals — the core behaviour a user relies on."""

from __future__ import annotations

import pytest

from model_router.models import TaskSignals
from model_router.registry import load_registry
from model_router.scorer import route


@pytest.fixture(scope="module")
def models():
    return load_registry()


def test_deep_reasoning_picks_opus(models):
    signals = TaskSignals(needed_capabilities=("reasoning",))
    rec = route(models, signals)
    assert rec.best is not None
    assert rec.best.model.id == "claude-opus-4-8"


def test_cheap_bulk_picks_cheap_model(models):
    signals = TaskSignals(
        needed_capabilities=("cheap_bulk",),
        cost_sensitive=True,
    )
    rec = route(models, signals)
    assert rec.best is not None
    # Should land on a cheap model: Haiku, or a cheap open model (GLM/DeepSeek/Llama).
    assert rec.best.model.cost_tier <= 2
    assert rec.best.model.has("cheap_bulk")


def test_open_only_excludes_closed_models(models):
    signals = TaskSignals(needed_capabilities=("coding",), open_only=True)
    rec = route(models, signals)
    assert rec.best is not None
    assert rec.best.model.open_weights
    # Every ranked candidate must be open.
    for alt in rec.alternatives:
        assert alt.model.open_weights
    # Closed models must appear in the excluded list.
    excluded_ids = {mid for mid, _ in rec.excluded}
    assert "claude-opus-4-8" in excluded_ids
    assert "gpt-class-large" in excluded_ids


def test_open_only_with_reasoning_picks_open_reasoner(models):
    signals = TaskSignals(needed_capabilities=("reasoning",), open_only=True)
    rec = route(models, signals)
    assert rec.best is not None
    assert rec.best.model.open_weights
    assert rec.best.model.has("reasoning")
    # deepseek-r1 and glm-4.6 are the open reasoners; one of them should win.
    assert rec.best.model.id in {"deepseek-r1", "glm-4.6"}


def test_max_context_filters_small_windows(models):
    # Require 300k context: 128k/200k models are filtered out.
    signals = TaskSignals(
        needed_capabilities=("long_context",),
        max_context=300_000,
    )
    rec = route(models, signals)
    assert rec.best is not None
    assert rec.best.model.context_window >= 300_000
    for model_id, reason in rec.excluded:
        if "context window" in reason:
            # the excluded ones genuinely have a smaller window
            small = next(m for m in models if m.id == model_id)
            assert small.context_window < 300_000


def test_est_context_cannot_exceed_window(models):
    # 250k estimated tokens excludes the 200k Haiku and 128k open models.
    signals = TaskSignals(est_context_tokens=250_000)
    rec = route(models, signals)
    assert rec.best is not None
    assert rec.best.model.context_window >= 250_000
    excluded_ids = {mid for mid, _ in rec.excluded}
    assert "claude-haiku-4-5" in excluded_ids  # 200k window


def test_latency_sensitive_prefers_fast_model(models):
    signals = TaskSignals(
        needed_capabilities=("coding",),
        latency_sensitive=True,
    )
    rec = route(models, signals)
    assert rec.best is not None
    # Top pick should be a fast model (speed tier 4-5).
    assert rec.best.model.speed_tier >= 4


def test_no_match_returns_none(models):
    # Impossible: open-only AND a context window bigger than any open model has.
    signals = TaskSignals(open_only=True, max_context=10_000_000)
    rec = route(models, signals)
    assert rec.best is None
    assert "No model" in rec.rationale


def test_breakdown_sums_to_score(models):
    signals = TaskSignals(needed_capabilities=("reasoning", "coding"))
    rec = route(models, signals)
    assert rec.best is not None
    assert round(sum(rec.best.breakdown.values()), 3) == rec.best.score
