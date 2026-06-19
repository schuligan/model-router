"""Signal inference + merge tests."""

from __future__ import annotations

from model_router.models import TaskSignals
from model_router.signals import infer_signals, merge


def test_infers_coding_and_reasoning():
    s = infer_signals("Refactor this Python repository and reason through the bug")
    assert s.needs("coding")
    assert s.needs("reasoning")


def test_infers_cheap_bulk_and_cost_sensitive():
    s = infer_signals("Classify thousands of support tickets as cheaply as possible")
    assert s.needs("cheap_bulk")
    assert s.cost_sensitive


def test_infers_latency():
    s = infer_signals("Need a fast, low-latency interactive chat assistant")
    assert s.latency_sensitive


def test_infers_open_only():
    s = infer_signals("Must be self-hosted and run locally, air-gapped")
    assert s.open_only


def test_infers_vision():
    s = infer_signals("Look at this screenshot and describe the chart")
    assert s.needs("vision")


def test_explicit_token_count_extracted():
    s = infer_signals("summarize a 500k token transcript")
    assert s.est_context_tokens == 500_000
    # large context auto-adds long_context
    assert s.needs("long_context")


def test_merge_unions_capabilities_and_ors_flags():
    inferred = infer_signals("write some code")  # coding
    overrides = TaskSignals(
        needed_capabilities=("vision",),
        cost_sensitive=True,
        open_only=True,
        max_context=128000,
        source="explicit",
    )
    merged = merge(inferred, overrides)
    assert merged.needs("coding")  # from inference
    assert merged.needs("vision")  # from override
    assert merged.cost_sensitive
    assert merged.open_only
    assert merged.max_context == 128000
