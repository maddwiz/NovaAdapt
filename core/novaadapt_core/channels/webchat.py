from __future__ import annotations

from typing import Any

from .base import ChannelAdapter, ChannelMessage, now_unix_ms


class WebChatChannelAdapter(ChannelAdapter):
    name = "webchat"

    def enabled(self) -> bool:
        return True

    def health(self) -> dict[str, Any]:
        return {"channel": self.name, "ok": True, "enabled": True, "mode": "local"}

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        sender = str(payload.get("sender") or payload.get("from") or "webchat-user").strip() or "webchat-user"
        text = str(payload.get("text") or payload.get("message") or "").strip()
        message_id = str(payload.get("message_id") or payload.get("id") or "").strip()
        metadata = {
            "room_id": str(payload.get("room_id") or "").strip(),
            "session_id": str(payload.get("session_id") or "").strip(),
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
        target = str(to or "").strip()
        body = str(text or "").strip()
        if not target:
            raise ValueError("'to' is required")
        if not body:
            raise ValueError("'text' is required")
        return {
            "ok": True,
            "channel": self.name,
            "to": target,
            "text": body,
            "delivered": True,
            "message_id": f"webchat-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
        }

