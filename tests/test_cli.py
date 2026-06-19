"""CLI tests — especially that --auto prints a bare, pipe-friendly model id."""

from __future__ import annotations

from model_router.cli import main
from model_router.registry import load_registry


def test_auto_prints_bare_id(capsys):
    code = main(["deep reasoning architecture task", "--auto"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    # Exactly one line, exactly a known model id, nothing else.
    assert "\n" not in out
    valid_ids = {m.id for m in load_registry()}
    assert out in valid_ids


def test_auto_open_only_returns_open_model(capsys):
    code = main(["coding task", "--auto", "--open-only"])
    assert code == 0
    out = capsys.readouterr().out.strip()
    model = next(m for m in load_registry() if m.id == out)
    assert model.open_weights


def test_models_subcommand_lists_registry(capsys, monkeypatch):
    # Force a wide console so rich doesn't truncate ids in the captured output.
    monkeypatch.setenv("COLUMNS", "200")
    from model_router import cli

    cli.console.width = 200
    code = main(["models"])
    assert code == 0
    out = capsys.readouterr().out
    assert "claude-opus-4-8" in out
    assert "glm-4.6" in out


def test_full_recommendation_output(capsys):
    code = main(["classify thousands of tickets cheaply", "--cheap"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Recommendation" in out
    assert "Rationale" in out


def test_no_args_prints_help(capsys):
    code = main([])
    assert code == 1


def test_auto_no_match_returns_nonzero(capsys):
    code = main(["anything", "--auto", "--open-only", "--max-context", "9000000"])
    assert code == 3
