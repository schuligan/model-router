---
name: model-route
description: >-
  Pick the right LLM for the current task before doing expensive work. Use when
  you're about to run a sub-task (classification, bulk generation, deep
  reasoning, a long-context summary, an agentic loop) and want to route it to the
  most cost-effective capable model instead of defaulting to one big model.
  Works for Anthropic Claude AND open models (GLM, Llama, DeepSeek).
---

# model-route

Wraps the local `model-router` tool so an agent can auto-pick — or switch — the
model for the task at hand. The router is pure local logic (no network, no key),
so calling it is cheap and safe.

## When to use this

Before kicking off a sub-task whose cost/quality trade-off matters:

- "Classify these 10k rows" → you want a cheap, fast model, not a frontier one.
- "Refactor this gnarly module and reason about the design" → you want depth.
- "Summarize this 400k-token doc" → you want a large enough context window.
- "This must run self-hosted / on-prem" → you want open weights only.

## How to call it

The router ships a `route` CLI. For agent use, prefer `--auto` — it prints **only
the chosen model id**, nothing else, so it's trivial to capture.

```bash
# Recommend (and switch to) a model for the current task
route "<describe the task in one line>" --auto
```

Add flags when you already know a constraint (they override inference):

| Flag              | Use when                                          |
|-------------------|---------------------------------------------------|
| `--cheap`         | Cost matters more than the last bit of quality     |
| `--fast`          | Latency-sensitive / interactive                    |
| `--reasoning`     | The task genuinely needs deep reasoning            |
| `--coding`        | Code generation / refactor / debugging             |
| `--vision`        | Images / screenshots / charts involved             |
| `--tool-use`      | Agentic / function-calling workload                |
| `--open-only`     | Must be open-weights / self-hostable               |
| `--max-context N` | Need at least N tokens of context window           |

To see the full reasoning (table + rationale + alternatives), drop `--auto`:

```bash
route "<task>"
```

## Recommended workflow

1. Summarize the imminent sub-task in one line.
2. Run `route "<that line>" [flags] --auto` to get a model id.
3. Use that model id for the sub-task (set it in your session / SDK call).
4. If you want to justify the choice to the user, run without `--auto` and relay
   the rationale.

## Examples

```bash
# Bulk classification → cheap/fast model
route "classify 50k support tickets by sentiment" --cheap --auto

# Hard reasoning → frontier model
route "redesign the auth system and reason through failure modes" --auto

# Self-hosted constraint → open model (e.g. GLM / DeepSeek / Llama)
route "coding agent that must run on-prem, air-gapped" --open-only --auto

# Long context → model with a big enough window
route "summarize a 400k-token transcript" --max-context 400000 --auto
```

## Notes

- **Works for open models too.** If the router returns something like `glm-4.6` or
  `deepseek-v3`, route the task to that open model exactly as you would a Claude
  model — the skill is provider-agnostic.
- **Edit the registry, not the code.** Available models, their capabilities, and
  the (approximate, relative) cost/speed tiers live in
  `model_router/registry.yaml`. Update it from current provider pricing when exact
  spend matters — the tiers are intentionally coarse and editable.
- The router never calls a network or needs an API key, so invoking it adds no
  cost or latency of its own.
