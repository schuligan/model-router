# Implementation Plan

How `model-router` is built, the scoring model, and the trade-offs behind it.

## Goal

Given a task, pick the best LLM from a config-driven registry by scoring task
signals — transparently, offline, and deterministically. Provider-agnostic
(Claude + open models). The router must run with zero network and no API key.

---

## Architecture

```
task text / flags
      │
      ▼
 signals.infer_signals()  ──┐         registry.load_registry()
      │ (heuristics)        │                  │  (validate YAML)
 CLI flags → overrides      │                  ▼
      │                     │            list[Model]
 signals.merge() ───────────┘                  │
      │                                         │
      ▼                                         ▼
            scorer.route(models, signals) ──────► Recommendation
                  │
        hard filters → exclude (with reason)
        weighted score → rank survivors
        rationale builder
```

Modules (each small, single-purpose, < 400 lines):

| File           | Responsibility                                              |
|----------------|-------------------------------------------------------------|
| `models.py`    | Immutable pydantic types: `Model`, `TaskSignals`, results   |
| `registry.py`  | Load + validate the YAML/JSON registry                      |
| `signals.py`   | Heuristic inference from text; merge explicit overrides     |
| `scorer.py`    | Hard filters + transparent weighted scoring + rationale     |
| `cli.py`       | `route` argparse CLI, `--auto`, `models`, rich output       |
| `registry.yaml`| The data — the only file users normally edit                |

---

## Registry schema

Each model entry:

| Field            | Type        | Notes                                            |
|------------------|-------------|--------------------------------------------------|
| `id`             | str         | Provider/SDK model id                            |
| `provider`       | str         | `anthropic`, `openai`, `zhipu`, `meta`, ...      |
| `open_weights`   | bool        | Self-hostable?                                   |
| `context_window` | int (>0)    | Max input+output tokens                          |
| `max_output`     | int? (>0)   | Optional output cap                              |
| `capabilities`   | tag list    | From a fixed, validated set (see below)          |
| `cost_tier`      | int 1–5     | RELATIVE, 1=cheapest. Approximate, editable.     |
| `speed_tier`     | int 1–5     | RELATIVE, 5=fastest. Approximate, editable.      |
| `notes`          | str         | Free text, surfaced in the rationale             |

Capability tags (closed set, typos rejected at load):
`reasoning`, `coding`, `vision`, `tool_use`, `long_context`, `cheap_bulk`.

**Why tiers, not prices:** dollar prices drift and asserting them as fact ages
badly. Coarse relative tiers are enough for *relative* selection, which is all the
router does. The config screams "edit me" so users keep it honest.

---

## Signal inference

`infer_signals(text)` is deliberately simple, transparent keyword matching — not an
LLM call — to keep the router offline and deterministic:

- **Capabilities**: per-tag keyword lists (e.g. "refactor"/"bug"/"api" → coding).
- **Context size**: regex for explicit counts ("500k tokens", "32000 context"),
  else a weak length-based estimate. ≥200k auto-adds `long_context`.
- **cost_sensitive / latency_sensitive / open_only**: keyword presence
  ("cheapest", "low latency", "self-hosted").

Explicit flags become a `TaskSignals` of overrides and are layered via `merge()`:
capabilities **union**, booleans **OR**, `max_context`/explicit context **win when
set**. Inference never erases an explicit instruction, and an explicit flag never
gets silently dropped.

---

## Scoring model

Two stages.

### 1. Hard filters (binary, with a reason)

A model is excluded outright if:
- `open_only` and it's closed-weights, or
- its `context_window` < `max_context`, or
- its `context_window` can't fit the estimated context tokens.

Excluded models are reported with their reason, so "why not X?" is always answerable.

### 2. Weighted additive score (survivors)

Named, tunable components (see `WEIGHTS` in `scorer.py`):

| Component          | Intuition                                                       |
|--------------------|-----------------------------------------------------------------|
| `capability_match` | +per needed capability present, −per missing (missing hurts more)|
| `cost`             | cheaper scores higher; dominant only when `cost_sensitive`       |
| `speed`            | faster scores higher; dominant only when `latency_sensitive`     |
| `context_headroom` | small bonus for comfortably fitting the context                 |
| `open_prior`       | tie-break nudge; small quality prior for closed frontier models  |
| `reasoning_depth`  | on reasoning tasks (when not cost-sensitive), prefer frontier    |

The score is just the sum; the per-component breakdown is returned so the rationale
can explain the win. Ties are broken deterministically (lower cost tier, then
higher speed, then id) for stable output.

**Design choice — capability presence is weighted heavily, not made a hard
filter.** A model missing a needed capability is penalised but not removed, so the
router can still surface a "closest available" pick (and explain the gap) rather
than returning nothing. Hard filters are reserved for genuine impossibilities
(can't self-host, can't fit context).

---

## Trade-offs

- **Heuristic inference vs. an LLM classifier.** Chose heuristics: offline,
  deterministic, free, testable. The cost is recall on oddly-worded tasks — which
  is exactly why explicit flags exist as an override path.
- **cost_tier as a reasoning proxy.** `reasoning_depth` uses cost tier as a coarse
  stand-in for capability depth. It's imperfect but transparent and easy to retune;
  a future version could add an explicit `quality_tier`.
- **Relative tiers vs. real benchmarks.** No benchmark numbers are baked in (they'd
  rot). The registry owner encodes their own judgment in the tiers.
- **Immutability everywhere.** All data models are `frozen=True`; the router returns
  new objects and never mutates inputs, keeping routing side-effect-free.

---

## Phased plan

- **Phase 1 (this repo):** registry + signal inference + scorer + CLI + tests. ✅
- **Phase 2:** optional live "explain" mode (prose rationale via the optional
  `anthropic` dep / env key).
- **Phase 3:** selectable scoring profiles (`--profile cost-first|quality-first`).
- **Phase 4:** `route serve` HTTP endpoint; price-sync helper for `cost_tier`.

---

## Testing

`pytest`, no network. Coverage targets the behaviours users rely on:

- Registry loads; bad tags / duplicates / missing files raise clearly.
- Signal inference detects capabilities, cost/latency/open flags, token counts.
- Scoring: deep-reasoning → Opus; cheap-bulk → a cheap model; `open_only` excludes
  closed models; `max_context`/estimated context respect windows; no-match returns
  `None`; the breakdown sums to the score.
- CLI: `--auto` emits a bare valid id; `models` lists the registry; help on no args.
