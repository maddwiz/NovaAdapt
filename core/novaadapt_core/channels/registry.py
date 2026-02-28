from __future__ import annotations

from typing import Any

from .base import ChannelAdapter
from .discord import DiscordChannelAdapter
from .googlechat import GoogleChatChannelAdapter
from .imessage import IMessageChannelAdapter
from .matrix import MatrixChannelAdapter
from .signal import SignalChannelAdapter
from .slack import SlackChannelAdapter
from .telegram import TelegramChannelAdapter
from .teams import TeamsChannelAdapter
from .webchat import WebChatChannelAdapter
from .whatsapp import WhatsAppChannelAdapter


class ChannelRegistry:
    def __init__(self, adapters: list[ChannelAdapter] | None = None) -> None:
        resolved = adapters if isinstance(adapters, list) else []
        self._adapters: dict[str, ChannelAdapter] = {}
        for adapter in resolved:
            name = str(getattr(adapter, "name", "")).strip().lower()
            if not name:
                continue
            self._adapters[name] = adapter

    def names(self) -> list[str]:
        return sorted(self._adapters.keys())

    def get(self, channel_name: str) -> ChannelAdapter | None:
        normalized = str(channel_name or "").strip().lower()
        if not normalized:
            return None
        return self._adapters.get(normalized)

    def list_channels(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name in self.names():
            adapter = self._adapters[name]
            health = adapter.health()
            item = health if isinstance(health, dict) else {}
            row = dict(item)
            row.setdefault("channel", name)
            row["enabled"] = bool(row.get("enabled", adapter.enabled()))
            out.append(row)
        return out

    def health(self, channel_name: str) -> dict[str, Any]:
        normalized = str(channel_name or "").strip().lower()
        adapter = self.get(normalized)
        if adapter is None:
            return {
                "ok": False,
                "channel": normalized,
                "error": f"unknown channel: {normalized}",
                "available_channels": self.names(),
            }
        payload = adapter.health()
        out = payload if isinstance(payload, dict) else {}
        result = dict(out)
        result.setdefault("channel", normalized)
        return result


def build_channel_registry() -> ChannelRegistry:
    return ChannelRegistry(
        adapters=[
            WebChatChannelAdapter(),
            IMessageChannelAdapter(),
            WhatsAppChannelAdapter(),
            TelegramChannelAdapter(),
            DiscordChannelAdapter(),
            SlackChannelAdapter(),
            SignalChannelAdapter(),
            TeamsChannelAdapter(),
            GoogleChatChannelAdapter(),
            MatrixChannelAdapter(),
        ]
    )
