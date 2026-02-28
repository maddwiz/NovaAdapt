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

DIRECT_WEBHOOK_CHANNELS = {"discord", "slack", "whatsapp", "telegram", "signal"}

CHANNEL_VERIFICATION_METHODS: dict[str, list[str]] = {
    "webchat": ["inbound_token"],
    "imessage": ["inbound_token"],
    "whatsapp": ["inbound_token", "whatsapp_signature"],
    "telegram": ["inbound_token", "telegram_secret_token", "telegram_hmac"],
    "discord": ["inbound_token", "discord_ed25519", "webhook_hmac"],
    "slack": ["inbound_token", "slack_signature"],
    "signal": ["inbound_token", "signal_hmac"],
    "teams": ["inbound_token"],
    "googlechat": ["inbound_token"],
    "matrix": ["inbound_token"],
}


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
            row["security"] = self._security_posture(name, adapter, row)
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
        result["security"] = self._security_posture(normalized, adapter, result)
        return result

    def _security_posture(self, name: str, adapter: ChannelAdapter, health_payload: dict[str, Any]) -> dict[str, Any]:
        inbound_token_configured = bool(health_payload.get("inbound_token_configured", False))
        if not inbound_token_configured:
            inbound_token_fn = getattr(adapter, "_inbound_token", None)
            if callable(inbound_token_fn):
                try:
                    inbound_token_configured = bool(str(inbound_token_fn()).strip())
                except Exception:
                    inbound_token_configured = False

        signature_required = bool(health_payload.get("require_signature", False))
        signature_configured = False
        for key, value in health_payload.items():
            key_name = str(key or "").strip().lower()
            if not key_name.endswith("_configured"):
                continue
            if key_name in {"configured", "token_configured", "default_channel_configured", "default_chat_id_configured"}:
                continue
            if key_name.endswith("token_configured") and "secret" not in key_name:
                continue
            if bool(value):
                signature_configured = True
                break

        methods = list(CHANNEL_VERIFICATION_METHODS.get(name, ["inbound_token"]))
        direct_webhook_supported = name in DIRECT_WEBHOOK_CHANNELS
        if signature_configured:
            recommended = next((m for m in methods if m != "inbound_token"), "inbound_token")
        elif inbound_token_configured:
            recommended = "inbound_token"
        else:
            recommended = "none"

        return {
            "inbound_token_configured": inbound_token_configured,
            "signature_configured": signature_configured,
            "signature_required": signature_required,
            "direct_webhook_supported": direct_webhook_supported,
            "supported_verification_methods": methods,
            "recommended_verification_method": recommended,
        }


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
