from __future__ import annotations

import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class DiscordChannelAdapter(ChannelAdapter):
    name = "discord"

    def __init__(self) -> None:
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_DISCORD_BOT_TOKEN", "")).strip()
        self.default_channel_id = str(os.getenv("NOVAADAPT_CHANNEL_DISCORD_DEFAULT_CHANNEL_ID", "")).strip()
        default_enabled = bool(self.token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_DISCORD_ENABLED", default_enabled)

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
        data = payload.get("d")
        if not isinstance(data, dict):
            data = payload
        author = data.get("author")
        if not isinstance(author, dict):
            author = {}
        sender = (
            str(author.get("username") or "").strip()
            or str(author.get("id") or "").strip()
            or str(data.get("user_id") or "").strip()
            or "discord-user"
        )
        text = str(data.get("content") or "").strip()
        message_id = str(data.get("id") or payload.get("id") or "").strip()
        metadata = {
            "channel_id": str(data.get("channel_id") or "").strip(),
            "guild_id": str(data.get("guild_id") or "").strip(),
            "author_id": str(author.get("id") or "").strip(),
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
            return {"ok": False, "channel": self.name, "error": "discord channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "discord bot token not configured"}
        channel_id = str(to or "").strip() or self.default_channel_id
        body = str(text or "").strip()
        if not channel_id:
            raise ValueError("'to' is required (discord channel id)")
        if not body:
            raise ValueError("'text' is required")
        endpoint = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        response = http_json_request(
            method="POST",
            url=endpoint,
            headers={"Authorization": f"Bot {self.token}"},
            payload={"content": body},
            timeout_seconds=15.0,
        )
        provider = dict(response.get("response") or {})
        message_id = str(provider.get("id") or "").strip()
        ok = bool(response.get("ok", False) and message_id)
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
            out["error"] = str(response.get("error") or provider.get("message") or "discord send failed")
        return out

