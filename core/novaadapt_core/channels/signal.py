from __future__ import annotations

import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class SignalChannelAdapter(ChannelAdapter):
    name = "signal"

    def __init__(self) -> None:
        self.base_url = str(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_BASE_URL", "http://127.0.0.1:8080")).strip().rstrip("/")
        self.sender = str(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_SENDER", "")).strip()
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_TOKEN", "")).strip()
        default_enabled = bool(self.base_url and self.sender)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_SIGNAL_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        configured = bool(self.base_url and self.sender)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and configured),
            "enabled": bool(self.enabled()),
            "configured": configured,
            "base_url": self.base_url,
            "sender_configured": bool(self.sender),
            "token_configured": bool(self.token),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        envelope = payload.get("envelope")
        if not isinstance(envelope, dict):
            envelope = payload
        data_message = envelope.get("dataMessage")
        if not isinstance(data_message, dict):
            data_message = {}
        sender = (
            str(envelope.get("sourceNumber") or "").strip()
            or str(payload.get("sender") or "").strip()
            or str(payload.get("from") or "").strip()
            or "signal-user"
        )
        text = (
            str(data_message.get("message") or "").strip()
            or str(payload.get("text") or "").strip()
            or str(payload.get("message") or "").strip()
        )
        message_id = (
            str(envelope.get("timestamp") or "").strip()
            or str(payload.get("message_id") or "").strip()
            or str(payload.get("id") or "").strip()
        )
        metadata = {
            "source_uuid": str(envelope.get("sourceUuid") or "").strip(),
            "source_device": str(envelope.get("sourceDevice") or "").strip(),
            "timestamp": str(envelope.get("timestamp") or "").strip(),
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
            return {"ok": False, "channel": self.name, "error": "signal channel disabled"}
        if not self.base_url:
            return {"ok": False, "channel": self.name, "error": "signal base url not configured"}
        if not self.sender:
            return {"ok": False, "channel": self.name, "error": "signal sender number not configured"}

        recipient = str(to or "").strip()
        body = str(text or "").strip()
        if not recipient:
            raise ValueError("'to' is required (signal phone number)")
        if not body:
            raise ValueError("'text' is required")

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = http_json_request(
            method="POST",
            url=f"{self.base_url}/v2/send",
            headers=headers,
            payload={
                "message": body,
                "number": self.sender,
                "recipients": [recipient],
            },
            timeout_seconds=20.0,
        )
        provider = dict(response.get("response") or {})
        ok = bool(response.get("ok", False)) and not bool(provider.get("error"))
        timestamp = str(provider.get("timestamp") or "").strip()
        out = {
            "ok": ok,
            "channel": self.name,
            "to": recipient,
            "text": body,
            "message_id": timestamp or f"signal-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not ok:
            out["error"] = str(response.get("error") or provider.get("error") or "signal send failed")
        return out
