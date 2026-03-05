from __future__ import annotations

import os

from ..flags import coerce_bool
from .actions import CanvasActionError, CanvasActionRouter
from .renderer import CanvasRenderResult, CanvasRenderer
from .server import CanvasSessionStore


def canvas_enabled(*, context: str = "api") -> bool:
    normalized = str(context or "api").strip().upper() or "API"
    global_enabled = coerce_bool(os.getenv("NOVAADAPT_ENABLE_CANVAS"), default=False)
    context_enabled = coerce_bool(os.getenv(f"NOVAADAPT_ENABLE_CANVAS_{normalized}"), default=False)
    return bool(global_enabled or context_enabled)


__all__ = [
    "CanvasActionError",
    "CanvasActionRouter",
    "CanvasRenderResult",
    "CanvasRenderer",
    "CanvasSessionStore",
    "canvas_enabled",
]
