from __future__ import annotations

import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class GoogleChatChannelAdapter(ChannelAdapter):
    name = "googlechat"

    def __init__(self) -> None:
        self.webhook_url = str(os.getenv("NOVAADAPT_CHANNEL_GOOGLECHAT_WEBHOOK_URL", "")).strip()
        default_enabled = bool(self.webhook_url)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_GOOGLECHAT_ENABLED", default_enabled)

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
        user_payload = payload.get("user")
        if not isinstance(user_payload, dict):
            user_payload = {}
        message_payload = payload.get("message")
        if not isinstance(message_payload, dict):
            message_payload = {}
        sender = (
            str(user_payload.get("displayName") or "").strip()
            or str(user_payload.get("name") or "").strip()
            or str(payload.get("sender") or "").strip()
            or "googlechat-user"
        )
        text = (
            str(message_payload.get("argumentText") or "").strip()
            or str(message_payload.get("text") or "").strip()
            or str(payload.get("text") or "").strip()
            or str(payload.get("message") or "").strip()
        )
        message_id = (
            str(message_payload.get("name") or "").strip()
            or str(payload.get("eventTime") or "").strip()
            or str(payload.get("id") or "").strip()
        )
        space_payload = payload.get("space")
        if not isinstance(space_payload, dict):
            space_payload = {}
        metadata = {
            "space_name": str(space_payload.get("name") or "").strip(),
            "space_type": str(space_payload.get("type") or "").strip(),
            "thread_name": str((message_payload.get("thread") or {}).get("name") or "").strip()
            if isinstance(message_payload.get("thread"), dict)
            else "",
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
            return {"ok": False, "channel": self.name, "error": "googlechat channel disabled"}
        if not self.webhook_url:
            return {"ok": False, "channel": self.name, "error": "google chat webhook url not configured"}
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
            "message_id": f"googlechat-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
            "provider_response": dict(response.get("response") or {}),
        }
        if not ok:
            out["error"] = str(response.get("error") or "google chat send failed")
        return out
