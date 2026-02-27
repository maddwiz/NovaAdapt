from __future__ import annotations

import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class TelegramChannelAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self) -> None:
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_TELEGRAM_BOT_TOKEN", "")).strip()
        self.default_chat_id = str(os.getenv("NOVAADAPT_CHANNEL_TELEGRAM_DEFAULT_CHAT_ID", "")).strip()
        default_enabled = bool(self.token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_TELEGRAM_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and self.token),
            "enabled": bool(self.enabled()),
            "configured": bool(self.token),
            "default_chat_id_configured": bool(self.default_chat_id),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        message = payload.get("message")
        if not isinstance(message, dict):
            message = payload.get("edited_message")
        if not isinstance(message, dict):
            message = payload
        from_payload = message.get("from")
        if not isinstance(from_payload, dict):
            from_payload = {}
        chat = message.get("chat")
        if not isinstance(chat, dict):
            chat = {}
        sender = (
            str(from_payload.get("username") or "").strip()
            or str(from_payload.get("id") or "").strip()
            or "telegram-user"
        )
        text = str(message.get("text") or message.get("caption") or "").strip()
        message_id = str(message.get("message_id") or payload.get("update_id") or "").strip()
        metadata = {
            "chat_id": str(chat.get("id") or "").strip(),
            "chat_type": str(chat.get("type") or "").strip(),
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
            return {"ok": False, "channel": self.name, "error": "telegram channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "telegram bot token not configured"}
        chat_id = str(to or "").strip() or self.default_chat_id
        body = str(text or "").strip()
        if not chat_id:
            raise ValueError("'to' is required (telegram chat_id)")
        if not body:
            raise ValueError("'text' is required")
        endpoint = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = http_json_request(
            method="POST",
            url=endpoint,
            payload={"chat_id": chat_id, "text": body},
            timeout_seconds=15.0,
        )
        provider = dict(response.get("response") or {})
        provider_ok = bool(provider.get("ok", False))
        message_payload = provider.get("result")
        message_id = ""
        if isinstance(message_payload, dict):
            message_id = str(message_payload.get("message_id") or "").strip()
        out = {
            "ok": bool(response.get("ok", False) and provider_ok),
            "channel": self.name,
            "to": chat_id,
            "text": body,
            "message_id": message_id,
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not out["ok"]:
            out["error"] = str(response.get("error") or provider.get("description") or "telegram send failed")
        return out

