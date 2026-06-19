"""Load and validate the model registry from YAML (or JSON).

The registry is the single source of truth for available models. This module
turns the raw file into validated `Model` objects and fails loudly on bad data.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from model_router.models import CAPABILITIES, Model

DEFAULT_REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


class RegistryError(ValueError):
    """Raised when the registry file is missing, malformed, or invalid."""


def _parse_raw(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def load_registry(path: str | Path | None = None) -> list[Model]:
    """Load, validate, and return the registry as a list of `Model`.

    Raises `RegistryError` on any problem (missing file, bad schema, unknown
    capability tag, duplicate ids) so misconfiguration never silently degrades
    routing quality.
    """
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH

    if not registry_path.exists():
        raise RegistryError(f"Registry file not found: {registry_path}")

    try:
        raw = _parse_raw(registry_path)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise RegistryError(f"Could not parse {registry_path}: {exc}") from exc

    if not isinstance(raw, dict) or "models" not in raw:
        raise RegistryError(
            f"{registry_path} must contain a top-level 'models:' list."
        )

    entries = raw["models"]
    if not isinstance(entries, list) or not entries:
        raise RegistryError(f"{registry_path} 'models' must be a non-empty list.")

    models: list[Model] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(entries):
        try:
            model = Model(**entry)
        except ValidationError as exc:
            raise RegistryError(
                f"Invalid model at index {index} in {registry_path}:\n{exc}"
            ) from exc

        unknown = set(model.capabilities) - set(CAPABILITIES)
        if unknown:
            raise RegistryError(
                f"Model '{model.id}' has unknown capability tags {sorted(unknown)}. "
                f"Allowed: {list(CAPABILITIES)}"
            )

        if model.id in seen_ids:
            raise RegistryError(f"Duplicate model id '{model.id}' in {registry_path}.")
        seen_ids.add(model.id)

        models.append(model)

    return models
