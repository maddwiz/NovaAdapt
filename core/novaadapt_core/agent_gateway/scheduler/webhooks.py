from __future__ import annotations

from typing import Any


class WebhookScheduler:
    def __init__(self) -> None:
        self._routes: dict[str, dict[str, Any]] = {}

    def register(self, event_name: str, payload_template: dict[str, Any]) -> None:
        key = str(event_name or "").strip().lower()
        if not key:
            raise ValueError("event_name is required")
        self._routes[key] = dict(payload_template if isinstance(payload_template, dict) else {})

    def trigger(self, event_name: str, *, event_payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
        key = str(event_name or "").strip().lower()
        template = self._routes.get(key)
        if template is None:
            return None
        merged = dict(template)
        merged["webhook_event"] = key
        if isinstance(event_payload, dict):
            merged["webhook_payload"] = dict(event_payload)
        return merged
