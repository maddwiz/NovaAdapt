from __future__ import annotations

import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class SlackChannelAdapter(ChannelAdapter):
    name = "slack"

    def __init__(self) -> None:
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_SLACK_BOT_TOKEN", "")).strip()
        self.default_channel_id = str(os.getenv("NOVAADAPT_CHANNEL_SLACK_DEFAULT_CHANNEL_ID", "")).strip()
        default_enabled = bool(self.token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_SLACK_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and self.token),
            "enabled": bool(self.enabled()),
            "configured": bool(self.token),
            "default_channel_configured": bool(self.default_channel_id),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        event = payload.get("event")
        if not isinstance(event, dict):
            event = payload
        sender = str(event.get("user") or payload.get("user") or "slack-user").strip() or "slack-user"
        text = str(event.get("text") or payload.get("text") or "").strip()
        message_id = str(event.get("client_msg_id") or event.get("ts") or payload.get("ts") or "").strip()
        metadata = {
            "channel_id": str(event.get("channel") or "").strip(),
            "thread_ts": str(event.get("thread_ts") or "").strip(),
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
            return {"ok": False, "channel": self.name, "error": "slack channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "slack bot token not configured"}
        channel_id = str(to or "").strip() or self.default_channel_id
        body = str(text or "").strip()
        if not channel_id:
            raise ValueError("'to' is required (slack channel id)")
        if not body:
            raise ValueError("'text' is required")
        response = http_json_request(
            method="POST",
            url="https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {self.token}"},
            payload={"channel": channel_id, "text": body},
            timeout_seconds=15.0,
        )
        provider = dict(response.get("response") or {})
        ok = bool(response.get("ok", False) and provider.get("ok", False))
        message_payload = provider.get("message")
        message_id = ""
        if isinstance(message_payload, dict):
            message_id = str(message_payload.get("client_msg_id") or message_payload.get("ts") or "").strip()
        if not message_id:
            message_id = str(provider.get("ts") or "").strip()
        out = {
            "ok": ok,
            "channel": self.name,
            "to": channel_id,
            "text": body,
            "message_id": message_id,
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not ok:
            out["error"] = str(response.get("error") or provider.get("error") or "slack send failed")
        return out

