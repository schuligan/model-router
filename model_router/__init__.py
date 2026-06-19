"""model-router — pick the right LLM for a task from a config-driven registry.

Public API:
    from model_router import load_registry, infer_signals, route, TaskSignals

The router is pure logic: no network, no API key required to run.
"""

from model_router.models import Model, Recommendation, ScoredModel, TaskSignals
from model_router.registry import DEFAULT_REGISTRY_PATH, load_registry
from model_router.scorer import route
from model_router.signals import infer_signals

__all__ = [
    "Model",
    "TaskSignals",
    "Recommendation",
    "ScoredModel",
    "load_registry",
    "DEFAULT_REGISTRY_PATH",
    "infer_signals",
    "route",
]

__version__ = "0.1.0"
