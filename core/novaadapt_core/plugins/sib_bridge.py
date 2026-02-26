from __future__ import annotations

from typing import Any

from .registry import PluginRegistry


class SIBBridge:
    """Thin typed wrapper around SIB-specific NovaBridge routes."""

    def __init__(self, registry: PluginRegistry, plugin_name: str = "sib_bridge") -> None:
        self.registry = registry
        self.plugin_name = str(plugin_name or "sib_bridge").strip() or "sib_bridge"

    def health(self) -> dict[str, Any]:
        return self.registry.health(self.plugin_name)

    def realm(self, player_id: str, realm: str) -> dict[str, Any]:
        return self.registry.call(
            self.plugin_name,
            route="/game/realm",
            payload={"player_id": str(player_id or ""), "realm": str(realm or "")},
            method="POST",
        )

    def companion_state(self, adapt_id: str, state: dict[str, Any]) -> dict[str, Any]:
        return self.registry.call(
            self.plugin_name,
            route="/game/companion/state",
            payload={"adapt_id": str(adapt_id or ""), "state": state if isinstance(state, dict) else {}},
            method="POST",
        )

    def companion_speak(self, adapt_id: str, text: str, channel: str = "in_game") -> dict[str, Any]:
        return self.registry.call(
            self.plugin_name,
            route="/game/companion/speak",
            payload={
                "adapt_id": str(adapt_id or ""),
                "text": str(text or ""),
                "channel": str(channel or "in_game"),
            },
            method="POST",
        )

    def phase_event(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.registry.call(
            self.plugin_name,
            route="/game/phase_event",
            payload={
                "event_type": str(event_type or ""),
                "payload": payload if isinstance(payload, dict) else {},
            },
            method="POST",
        )

    def resonance_start(self, player_id: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.registry.call(
            self.plugin_name,
            route="/game/resonance/start",
            payload={
                "player_id": str(player_id or ""),
                "player_profile": profile if isinstance(profile, dict) else {},
            },
            method="POST",
        )

    def resonance_result(self, player_id: str, adapt_id: str, accepted: bool) -> dict[str, Any]:
        return self.registry.call(
            self.plugin_name,
            route="/game/resonance/result",
            payload={
                "player_id": str(player_id or ""),
                "adapt_id": str(adapt_id or ""),
                "accepted": bool(accepted),
            },
            method="POST",
        )
