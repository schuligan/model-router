"""Transparent weighted scoring over the registry.

Every model that survives the hard filters gets a score built from clearly
named, additive components. The per-component breakdown is returned so the
rationale can explain *why* a model won — no black box.

Scoring components (all tunable via the WEIGHTS dict):

  capability_match : + for each needed capability the model has
                     - penalty for each needed capability it LACKS
  cost             : cheaper models score higher when cost_sensitive
  speed            : faster models score higher when latency_sensitive
  context_headroom : small bonus for comfortably fitting the estimated context
  open_bonus       : small nudge toward open models when open_only is set
                     (open_only is also a hard filter; this just orders ties)
  reasoning_depth  : when the task needs reasoning AND is not cost-sensitive,
                     prefer higher-tier (frontier) models — cost_tier is used as
                     a coarse proxy for reasoning capability. Suppressed when the
                     user has signalled they care about cost.

Hard filters (remove a model entirely, with a reason):

  open_only        : drop closed-weight models
  max_context      : drop models whose context_window < required max_context
  context_fit      : drop models that cannot fit the estimated context
"""

from __future__ import annotations

from model_router.models import Model, Recommendation, ScoredModel, TaskSignals

# ── Tunable weights ──────────────────────────────────────────────────────────
# Edit these to change the router's personality. They are deliberately exposed
# and documented rather than buried as magic numbers.
WEIGHTS: dict[str, float] = {
    "capability_have": 10.0,     # reward per matched needed capability
    "capability_missing": 12.0,  # penalty per missing needed capability
    "cost": 6.0,                 # max swing from the cost component
    "speed": 6.0,                # max swing from the speed component
    "context_headroom": 2.0,     # bonus for comfortably fitting context
    "open_bonus": 1.5,           # tie-break nudge toward open models
    # Baseline quality prior: closed frontier models tend to be stronger.
    # Small, and only breaks ties between otherwise-equal candidates.
    "closed_quality_prior": 1.0,
    # When reasoning is needed and cost isn't a concern, lean toward the
    # higher-tier (frontier) models. Coarse proxy: higher cost_tier == deeper.
    "reasoning_depth": 4.0,
}

# A model needs this much context headroom (multiplier on est tokens) to earn
# the full headroom bonus. Below 1.0 it can't fit at all (hard-filtered).
HEADROOM_TARGET = 1.5


def _cost_component(model: Model, signals: TaskSignals) -> float:
    """Cheaper => higher. Only material when the task is cost-sensitive.

    cost_tier is 1..5 (1 cheapest). Normalise to 0..1 where 1 is cheapest.
    """
    cheapness = (5 - model.cost_tier) / 4.0  # tier 1 -> 1.0, tier 5 -> 0.0
    weight = WEIGHTS["cost"]
    if not signals.cost_sensitive:
        weight *= 0.25  # cost still matters a little, but not dominant
    return cheapness * weight


def _speed_component(model: Model, signals: TaskSignals) -> float:
    """Faster => higher. Only material when latency-sensitive."""
    speediness = (model.speed_tier - 1) / 4.0  # tier 5 -> 1.0, tier 1 -> 0.0
    weight = WEIGHTS["speed"]
    if not signals.latency_sensitive:
        weight *= 0.25
    return speediness * weight


def _capability_component(model: Model, signals: TaskSignals) -> float:
    score = 0.0
    for capability in signals.needed_capabilities:
        if model.has(capability):
            score += WEIGHTS["capability_have"]
        else:
            score -= WEIGHTS["capability_missing"]
    return score


def _context_component(model: Model, signals: TaskSignals) -> float:
    if signals.est_context_tokens <= 0:
        return 0.0
    headroom = model.context_window / signals.est_context_tokens
    if headroom >= HEADROOM_TARGET:
        return WEIGHTS["context_headroom"]
    # Fits, but tight — scale the bonus down.
    return WEIGHTS["context_headroom"] * max(0.0, (headroom - 1.0) / (HEADROOM_TARGET - 1.0))


def _open_component(model: Model, signals: TaskSignals) -> float:
    if model.open_weights:
        return WEIGHTS["open_bonus"] if signals.open_only else 0.0
    # Closed model: small quality prior, but it never applies under open_only
    # (those are filtered out before scoring).
    return WEIGHTS["closed_quality_prior"]


def _reasoning_component(model: Model, signals: TaskSignals) -> float:
    """Favour frontier (higher cost_tier) models on reasoning tasks, unless the
    user is cost-sensitive (in which case depth shouldn't override thrift)."""
    if not signals.needs("reasoning") or not model.has("reasoning"):
        return 0.0
    if signals.cost_sensitive:
        return 0.0
    depth = (model.cost_tier - 1) / 4.0  # tier 5 -> 1.0, tier 1 -> 0.0
    return depth * WEIGHTS["reasoning_depth"]


def _filter_reason(model: Model, signals: TaskSignals) -> str | None:
    """Return a human-readable reason to exclude the model, or None to keep it."""
    if signals.open_only and not model.open_weights:
        return "closed weights (open-only required)"
    if signals.max_context is not None and model.context_window < signals.max_context:
        return (
            f"context window {model.context_window:,} < required "
            f"{signals.max_context:,}"
        )
    if (
        signals.est_context_tokens > 0
        and model.context_window < signals.est_context_tokens
    ):
        return (
            f"context window {model.context_window:,} cannot fit estimated "
            f"{signals.est_context_tokens:,} tokens"
        )
    return None


def _score_model(model: Model, signals: TaskSignals) -> ScoredModel:
    breakdown = {
        "capability_match": round(_capability_component(model, signals), 3),
        "cost": round(_cost_component(model, signals), 3),
        "speed": round(_speed_component(model, signals), 3),
        "context_headroom": round(_context_component(model, signals), 3),
        "open_prior": round(_open_component(model, signals), 3),
        "reasoning_depth": round(_reasoning_component(model, signals), 3),
    }
    total = round(sum(breakdown.values()), 3)

    reasons: list[str] = []
    have = [c for c in signals.needed_capabilities if model.has(c)]
    missing = [c for c in signals.needed_capabilities if not model.has(c)]
    if have:
        reasons.append("covers " + ", ".join(have))
    if missing:
        reasons.append("MISSING " + ", ".join(missing))
    if signals.cost_sensitive:
        reasons.append(f"cost tier {model.cost_tier}/5")
    if signals.latency_sensitive:
        reasons.append(f"speed tier {model.speed_tier}/5")

    return ScoredModel(
        model=model,
        score=total,
        breakdown=breakdown,
        reasons=tuple(reasons),
    )


def _build_rationale(rec_best: ScoredModel | None, signals: TaskSignals) -> str:
    if rec_best is None:
        return "No model in the registry satisfies the hard constraints."

    m = rec_best.model
    parts = [f"Chose {m.id} ({m.provider})."]

    if signals.needed_capabilities:
        parts.append("Task needs: " + ", ".join(signals.needed_capabilities) + ".")
    constraints = []
    if signals.open_only:
        constraints.append("open-source/self-hostable")
    if signals.cost_sensitive:
        constraints.append("cost-sensitive")
    if signals.latency_sensitive:
        constraints.append("latency-sensitive")
    if signals.max_context:
        constraints.append(f"context >= {signals.max_context:,}")
    if signals.est_context_tokens:
        constraints.append(f"~{signals.est_context_tokens:,} est tokens")
    if constraints:
        parts.append("Constraints: " + ", ".join(constraints) + ".")

    parts.append(
        f"Relative cost tier {m.cost_tier}/5 (1=cheapest), "
        f"speed tier {m.speed_tier}/5 (5=fastest)."
    )
    if m.notes:
        parts.append(m.notes)
    return " ".join(parts)


def route(
    models: list[Model],
    signals: TaskSignals,
    top_k: int = 3,
) -> Recommendation:
    """Score every model against the signals and return a `Recommendation`.

    Models failing a hard filter are excluded (with a reason). The survivors
    are ranked by score; ties broken deterministically by lower cost tier,
    then higher speed tier, then id, for stable output.
    """
    scored: list[ScoredModel] = []
    excluded: list[tuple[str, str]] = []

    for model in models:
        reason = _filter_reason(model, signals)
        if reason is not None:
            excluded.append((model.id, reason))
            continue
        scored.append(_score_model(model, signals))

    scored.sort(
        key=lambda s: (-s.score, s.model.cost_tier, -s.model.speed_tier, s.model.id)
    )

    best = scored[0] if scored else None
    alternatives = tuple(scored[1:top_k]) if len(scored) > 1 else ()

    return Recommendation(
        signals=signals,
        best=best,
        alternatives=alternatives,
        excluded=tuple(excluded),
        rationale=_build_rationale(best, signals),
    )
