from __future__ import annotations

from typing import Any, Callable


class CanvasActionError(RuntimeError):
    pass


CanvasActionHandler = Callable[[dict[str, Any]], dict[str, Any]]


class CanvasActionRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, CanvasActionHandler] = {}

    def register(self, action: str, handler: CanvasActionHandler) -> None:
        normalized = str(action or "").strip().lower()
        if not normalized:
            raise ValueError("'action' is required")
        self._handlers[normalized] = handler

    def list_actions(self) -> list[str]:
        return sorted(self._handlers.keys())

    def dispatch(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        if not normalized:
            raise ValueError("'action' is required")
        handler = self._handlers.get(normalized)
        if handler is None:
            raise CanvasActionError(f"unknown canvas action: {normalized}")
        raw = handler(dict(payload or {}))
        if not isinstance(raw, dict):
            raise CanvasActionError(f"canvas action '{normalized}' must return an object")
        return raw
