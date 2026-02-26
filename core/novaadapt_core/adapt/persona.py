from __future__ import annotations

from typing import Any

from .toggle import DEFAULT_TOGGLE_MODE


class AdaptPersonaEngine:
    """Build lightweight persona context for planning and dialogue style."""

    def build_context(
        self,
        *,
        adapt_id: str,
        toggle_mode: str | None,
        bond_verified: bool | None,
        identity_profile: dict[str, Any] | None,
        cached_bond: dict[str, Any] | None,
    ) -> dict[str, Any]:
        mode = str(toggle_mode or DEFAULT_TOGGLE_MODE).strip().lower() or DEFAULT_TOGGLE_MODE
        profile = dict(identity_profile) if isinstance(identity_profile, dict) else {}
        cache = dict(cached_bond) if isinstance(cached_bond, dict) else {}

        bond_strength = 0.0
        raw_strength = profile.get("bond_strength")
        try:
            bond_strength = float(raw_strength)
        except Exception:
            bond_strength = 0.0

        style = "concise"
        if mode == "silent":
            style = "nonverbal"
        elif mode == "in_game_only":
            style = "in_world"
        elif mode == "free_speak":
            style = "expressive"

        trust_band = "forming"
        if bond_strength >= 75:
            trust_band = "deeply_bonded"
        elif bond_strength >= 35:
            trust_band = "bonded"

        return {
            "adapt_id": str(adapt_id or "").strip(),
            "toggle_mode": mode,
            "bond_verified": bool(bond_verified) if bond_verified is not None else bool(cache.get("verified", False)),
            "trust_band": trust_band,
            "communication_style": style,
            "element": str(profile.get("element", "")),
            "subclass": str(profile.get("subclass", "")),
            "form_stage": str(profile.get("form_stage", "")),
        }
