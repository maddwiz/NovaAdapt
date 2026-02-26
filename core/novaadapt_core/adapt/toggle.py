from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOGGLE_MODES = {"free_speak", "in_game_only", "ask_only", "silent"}
DEFAULT_TOGGLE_MODE = "ask_only"


def _default_state_path() -> Path:
    env_path = str(os.getenv("NOVAADAPT_ADAPT_TOGGLE_PATH", "")).strip()
    if env_path:
        return Path(env_path)
    return Path.home() / ".novaadapt" / "adapt_toggles.json"


class AdaptToggleStore:
    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = state_path or _default_state_path()
        self._lock = threading.Lock()

    def get(self, adapt_id: str) -> dict[str, Any]:
        normalized = str(adapt_id or "").strip()
        if not normalized:
            raise ValueError("'adapt_id' is required")
        data = self._load()
        item = data.get(normalized)
        if not isinstance(item, dict):
            return {
                "adapt_id": normalized,
                "mode": DEFAULT_TOGGLE_MODE,
                "source": "default",
            }
        mode = str(item.get("mode", DEFAULT_TOGGLE_MODE)).strip().lower() or DEFAULT_TOGGLE_MODE
        if mode not in TOGGLE_MODES:
            mode = DEFAULT_TOGGLE_MODE
        return {
            "adapt_id": normalized,
            "mode": mode,
            "updated_at": item.get("updated_at"),
            "source": item.get("source", "local"),
        }

    def get_mode(self, adapt_id: str) -> str:
        return str(self.get(adapt_id).get("mode", DEFAULT_TOGGLE_MODE))

    def set(self, adapt_id: str, mode: str, *, source: str = "local") -> dict[str, Any]:
        normalized = str(adapt_id or "").strip()
        if not normalized:
            raise ValueError("'adapt_id' is required")
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode not in TOGGLE_MODES:
            raise ValueError(f"invalid mode '{mode}'. valid: {sorted(TOGGLE_MODES)}")

        updated = {
            "mode": normalized_mode,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source or "local").strip() or "local",
        }

        with self._lock:
            data = self._load()
            data[normalized] = updated
            self._save(data)

        return {
            "adapt_id": normalized,
            **updated,
        }

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
