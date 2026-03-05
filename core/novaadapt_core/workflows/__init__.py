from __future__ import annotations

import os

from ..flags import coerce_bool
from .checkpoints import WorkflowCheckpointStore
from .engine import WorkflowEngine
from .store import WorkflowRecord, WorkflowStore


def workflows_enabled(*, context: str = "api") -> bool:
    normalized = str(context or "api").strip().upper() or "API"
    global_enabled = coerce_bool(os.getenv("NOVAADAPT_ENABLE_WORKFLOWS"), default=False)
    context_enabled = coerce_bool(os.getenv(f"NOVAADAPT_ENABLE_WORKFLOWS_{normalized}"), default=False)
    return bool(global_enabled or context_enabled)


__all__ = [
    "WorkflowCheckpointStore",
    "WorkflowEngine",
    "WorkflowRecord",
    "WorkflowStore",
    "workflows_enabled",
]
