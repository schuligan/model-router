"""`route` — the model-router command-line interface.

Examples
--------
    route "refactor this large Rust codebase and add tests"
    route "classify 10k support tickets, cheapest option" --auto
    route "agent that must run fully self-hosted" --open-only
    route models
    route "summarize a 500k-token transcript" --max-context 300000

`--auto` prints ONLY the chosen model id, so it is pipe-friendly:

    MODEL=$(route "deep reasoning task" --auto)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from model_router.models import TaskSignals
from model_router.registry import RegistryError, load_registry
from model_router.scorer import route
from model_router.signals import infer_signals, merge

console = Console()
err_console = Console(stderr=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="route",
        description="Pick the right LLM for a task from a config-driven registry.",
    )
    parser.add_argument(
        "task",
        nargs="?",
        help='Free-text task description, or the literal word "models" to list '
        "the registry.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Path to a custom registry YAML/JSON (default: bundled registry).",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Print only the chosen model id (pipe-friendly).",
    )
    # Explicit signal overrides
    parser.add_argument("--cheap", action="store_true", help="Force cost-sensitive.")
    parser.add_argument(
        "--fast", action="store_true", help="Force latency-sensitive."
    )
    parser.add_argument(
        "--reasoning", action="store_true", help="Require reasoning capability."
    )
    parser.add_argument(
        "--coding", action="store_true", help="Require coding capability."
    )
    parser.add_argument(
        "--vision", action="store_true", help="Require vision capability."
    )
    parser.add_argument(
        "--tool-use", action="store_true", help="Require tool-use capability."
    )
    parser.add_argument(
        "--open-only",
        action="store_true",
        help="Only consider open-weights / self-hostable models.",
    )
    parser.add_argument(
        "--max-context",
        type=int,
        default=None,
        help="Require a context window of at least N tokens.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="How many ranked models to show (default 3).",
    )
    return parser


def _overrides_from_args(args: argparse.Namespace) -> TaskSignals:
    needed: list[str] = []
    if args.reasoning:
        needed.append("reasoning")
    if args.coding:
        needed.append("coding")
    if args.vision:
        needed.append("vision")
    if args.tool_use:
        needed.append("tool_use")

    return TaskSignals(
        needed_capabilities=tuple(needed),  # type: ignore[arg-type]
        cost_sensitive=args.cheap,
        latency_sensitive=args.fast,
        open_only=args.open_only,
        max_context=args.max_context,
        source="explicit",
    )


def _print_models_table(models: list) -> None:
    table = Table(title="Model registry", header_style="bold")
    table.add_column("id", style="bold cyan")
    table.add_column("provider")
    table.add_column("open", justify="center")
    table.add_column("context", justify="right")
    table.add_column("cost", justify="center")
    table.add_column("speed", justify="center")
    table.add_column("capabilities")
    for m in models:
        table.add_row(
            m.id,
            m.provider,
            "yes" if m.open_weights else "no",
            f"{m.context_window:,}",
            f"{m.cost_tier}/5",
            f"{m.speed_tier}/5",
            ", ".join(m.capabilities) or "-",
        )
    console.print(table)
    console.print(
        "[dim]Cost/speed tiers are approximate and editable in the registry "
        "(1=cheapest/slowest, 5=priciest/fastest).[/dim]"
    )


def _print_recommendation(rec, top: int) -> None:
    if rec.best is None:
        err_console.print("[bold red]No model satisfies the constraints.[/bold red]")
        for model_id, reason in rec.excluded:
            err_console.print(f"  [dim]excluded {model_id}: {reason}[/dim]")
        return

    table = Table(title="Recommendation", header_style="bold")
    table.add_column("rank", justify="right")
    table.add_column("model", style="bold cyan")
    table.add_column("provider")
    table.add_column("score", justify="right")
    table.add_column("cost", justify="center")
    table.add_column("speed", justify="center")
    table.add_column("why")

    ranked = [rec.best, *rec.alternatives][:top]
    for index, scored in enumerate(ranked, start=1):
        marker = "[green]★[/green]" if index == 1 else str(index)
        table.add_row(
            marker,
            scored.model.id,
            scored.model.provider,
            f"{scored.score:g}",
            f"{scored.model.cost_tier}/5",
            f"{scored.model.speed_tier}/5",
            "; ".join(scored.reasons) or "-",
        )
    console.print(table)
    console.print(f"\n[bold]Rationale:[/bold] {rec.rationale}")

    if rec.excluded:
        console.print("\n[dim]Excluded by hard filters:[/dim]")
        for model_id, reason in rec.excluded:
            console.print(f"  [dim]- {model_id}: {reason}[/dim]")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        models = load_registry(args.registry)
    except RegistryError as exc:
        err_console.print(f"[bold red]Registry error:[/bold red] {exc}")
        return 2

    if args.task is None:
        parser.print_help()
        return 1

    if args.task.strip().lower() == "models":
        _print_models_table(models)
        return 0

    inferred = infer_signals(args.task)
    overrides = _overrides_from_args(args)
    signals = merge(inferred, overrides)

    rec = route(models, signals, top_k=args.top)

    if args.auto:
        if rec.best is None:
            err_console.print("no-match")
            return 3
        # Bare id only — pipe-friendly.
        print(rec.best.model.id)
        return 0

    _print_recommendation(rec, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
