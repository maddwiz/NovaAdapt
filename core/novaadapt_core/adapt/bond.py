from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _default_state_path() -> Path:
    env_path = str(os.getenv("NOVAADAPT_ADAPT_BOND_CACHE_PATH", "")).strip()
    if env_path:
        return Path(env_path)
    return Path.home() / ".novaadapt" / "adapt_bonds.json"


class AdaptBondCache:
    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path or _default_state_path()
        self._lock = threading.Lock()

    def get(self, adapt_id: str) -> dict[str, Any] | None:
        normalized = str(adapt_id or "").strip()
        if not normalized:
            raise ValueError("'adapt_id' is required")
        payload = self._load().get(normalized)
        if isinstance(payload, dict):
            return dict(payload)
        return None

    def verify_cached(self, adapt_id: str, player_id: str) -> bool:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt or not normalized_player:
            return False
        current = self.get(normalized_adapt)
        if not isinstance(current, dict):
            return False
        return str(current.get("player_id", "")) == normalized_player and bool(current.get("verified", False))

    def remember(
        self,
        adapt_id: str,
        player_id: str,
        *,
        verified: bool,
        profile: dict[str, Any] | None = None,
        source: str = "novaprime",
    ) -> dict[str, Any]:
        normalized_adapt = str(adapt_id or "").strip()
        normalized_player = str(player_id or "").strip()
        if not normalized_adapt:
            raise ValueError("'adapt_id' is required")
        if not normalized_player:
            raise ValueError("'player_id' is required")

        payload = {
            "adapt_id": normalized_adapt,
            "player_id": normalized_player,
            "verified": bool(verified),
            "profile": dict(profile) if isinstance(profile, dict) else {},
            "source": str(source or "novaprime").strip() or "novaprime",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            state = self._load()
            state[normalized_adapt] = payload
            self._save(state)

        return payload

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.state_path.exists():
            return {}
        try:
            raw = self.state_path.read_text(encoding="utf-8")
        except Exception:
            return {}
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for key, value in parsed.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            out[key] = dict(value)
        return out

    def _save(self, payload: dict[str, dict[str, Any]]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)
        self.state_path.write_text(encoded + "\n", encoding="utf-8")
