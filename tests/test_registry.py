"""Registry loading and validation tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from model_router.registry import RegistryError, load_registry


def test_bundled_registry_loads():
    models = load_registry()
    assert len(models) >= 5
    ids = {m.id for m in models}
    # Anthropic models present with correct ids.
    assert "claude-opus-4-8" in ids
    assert "claude-sonnet-4-6" in ids
    assert "claude-haiku-4-5" in ids
    # At least one open model present.
    assert any(m.open_weights for m in models)
    # At least one closed model present.
    assert any(not m.open_weights for m in models)


def test_registry_has_open_and_glm_and_deepseek():
    ids = {m.id for m in load_registry()}
    assert "glm-4.6" in ids
    assert "deepseek-v3" in ids
    assert any(i.startswith("llama") for i in ids)


def test_unknown_capability_rejected(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent(
            """
            models:
              - id: x
                provider: test
                context_window: 1000
                capabilities: [reasoning, telepathy]
                cost_tier: 1
                speed_tier: 1
            """
        )
    )
    # Pydantic's Literal validation rejects it during model construction; the
    # belt-and-suspenders check in registry.py covers the same case. Either way
    # it surfaces as a RegistryError mentioning the bad tag.
    with pytest.raises(RegistryError, match="telepathy"):
        load_registry(bad)


def test_duplicate_id_rejected(tmp_path: Path):
    dup = tmp_path / "dup.yaml"
    dup.write_text(
        textwrap.dedent(
            """
            models:
              - id: x
                provider: test
                context_window: 1000
                cost_tier: 1
                speed_tier: 1
              - id: x
                provider: test
                context_window: 2000
                cost_tier: 2
                speed_tier: 2
            """
        )
    )
    with pytest.raises(RegistryError, match="Duplicate model id"):
        load_registry(dup)


def test_missing_file():
    with pytest.raises(RegistryError, match="not found"):
        load_registry("/no/such/registry.yaml")


def test_json_registry_loads(tmp_path: Path):
    j = tmp_path / "reg.json"
    j.write_text(
        '{"models": [{"id": "a", "provider": "p", "context_window": 1000, '
        '"cost_tier": 1, "speed_tier": 5, "capabilities": ["coding"]}]}'
    )
    models = load_registry(j)
    assert models[0].id == "a"
    assert models[0].has("coding")
