from __future__ import annotations

import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class TeamsChannelAdapter(ChannelAdapter):
    name = "teams"

    def __init__(self) -> None:
        self.webhook_url = str(os.getenv("NOVAADAPT_CHANNEL_TEAMS_WEBHOOK_URL", "")).strip()
        default_enabled = bool(self.webhook_url)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_TEAMS_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        configured = bool(self.webhook_url)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and configured),
            "enabled": bool(self.enabled()),
            "configured": configured,
            "webhook_configured": configured,
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        sender = (
            str(payload.get("from") or "").strip()
            or str(payload.get("sender") or "").strip()
            or str(payload.get("user") or "").strip()
            or "teams-user"
        )
        text = (
            str(payload.get("text") or "").strip()
            or str(payload.get("message") or "").strip()
            or str(payload.get("summary") or "").strip()
        )
        message_id = (
            str(payload.get("id") or "").strip()
            or str(payload.get("message_id") or "").strip()
            or str(payload.get("etag") or "").strip()
        )
        metadata = {
            "conversation_id": str(payload.get("conversationId") or "").strip(),
            "tenant_id": str(payload.get("tenantId") or "").strip(),
            "service_url": str(payload.get("serviceUrl") or "").strip(),
        }
        return ChannelMessage(
            channel=self.name,
            sender=sender,
            text=text,
            message_id=message_id,
            received_at_ms=now_unix_ms(),
            metadata=metadata,
        )

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "teams channel disabled"}
        if not self.webhook_url:
            return {"ok": False, "channel": self.name, "error": "teams webhook url not configured"}
        target = str(to or "").strip()
        body = str(text or "").strip()
        if not target:
            raise ValueError("'to' is required")
        if not body:
            raise ValueError("'text' is required")

        response = http_json_request(
            method="POST",
            url=self.webhook_url,
            payload={"text": body},
            timeout_seconds=15.0,
        )
        ok = bool(response.get("ok", False))
        out = {
            "ok": ok,
            "channel": self.name,
            "to": target,
            "text": body,
            "message_id": f"teams-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
            "provider_response": dict(response.get("response") or {}),
        }
        if not ok:
            out["error"] = str(response.get("error") or "teams send failed")
        return out
