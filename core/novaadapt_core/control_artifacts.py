from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True, default=str))


def _string_preview(value: object, limit: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def _action_target(action: dict[str, Any]) -> str:
    for key in ("target", "selector", "entity_id", "url", "package", "bundle_id", "text"):
        value = action.get(key)
        if value not in (None, ""):
            return str(value)
    if action.get("x") is not None and action.get("y") is not None:
        try:
            return f"{int(action.get('x'))},{int(action.get('y'))}"
        except Exception:
            return f"{action.get('x')},{action.get('y')}"
    return ""


class ControlArtifactStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.records_dir = self.root_dir / "records"
        self.previews_dir = self.root_dir / "previews"
        self._lock = threading.RLock()
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.previews_dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        control_type: str,
        status: str,
        output: str,
        action: dict[str, Any],
        dangerous: bool = False,
        goal: str = "",
        platform: str = "",
        transport: str = "",
        model: str = "",
        model_id: str = "",
        preview_png: bytes | None = None,
        data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        normalized_action = _json_safe(dict(action))

        record: dict[str, Any] = {
            "artifact_id": artifact_id,
            "created_at": created_at,
            "control_type": str(control_type or "").strip().lower() or "control",
            "status": str(status or "").strip() or "unknown",
            "dangerous": bool(dangerous),
            "goal": str(goal or "").strip(),
            "platform": str(platform or "").strip().lower(),
            "transport": str(transport or "").strip().lower(),
            "output": str(output or ""),
            "output_preview": _string_preview(output),
            "action": normalized_action,
            "action_type": str(normalized_action.get("type") or "").strip().lower(),
            "target": _action_target(normalized_action),
            "model": str(model or "").strip(),
            "model_id": str(model_id or "").strip(),
            "preview_available": bool(preview_png),
            "preview_path": f"/control/artifacts/{artifact_id}/preview" if preview_png else "",
            "detail_path": f"/control/artifacts/{artifact_id}",
        }
        if isinstance(data, dict) and data:
            record["data"] = _json_safe(data)
        if isinstance(metadata, dict) and metadata:
            record["metadata"] = _json_safe(metadata)

        if preview_png:
            preview_name = f"{artifact_id}.png"
            with self._lock:
                (self.previews_dir / preview_name).write_bytes(preview_png)
            record["_preview_file"] = preview_name

        with self._lock:
            (self.records_dir / f"{artifact_id}.json").write_text(
                json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return self._public_summary(record)

    def list(self, *, limit: int = 10, control_type: str | None = None) -> list[dict[str, Any]]:
        normalized_type = str(control_type or "").strip().lower()
        rows: list[dict[str, Any]] = []
        with self._lock:
            for path in self.records_dir.glob("*.json"):
                record = self._read_record_locked(path)
                if record is None:
                    continue
                if normalized_type and str(record.get("control_type") or "").strip().lower() != normalized_type:
                    continue
                rows.append(self._public_summary(record))
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows[: max(1, int(limit))]

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        normalized_id = str(artifact_id or "").strip()
        if not normalized_id:
            return None
        with self._lock:
            record = self._read_record_locked(self.records_dir / f"{normalized_id}.json")
        if record is None:
            return None
        return self._public_record(record)

    def read_preview(self, artifact_id: str) -> tuple[bytes, str] | None:
        normalized_id = str(artifact_id or "").strip()
        if not normalized_id:
            return None
        with self._lock:
            record = self._read_record_locked(self.records_dir / f"{normalized_id}.json")
            if record is None:
                return None
            preview_name = str(record.get("_preview_file") or "").strip()
            if not preview_name:
                return None
            preview_path = self.previews_dir / preview_name
            if not preview_path.exists():
                return None
            return preview_path.read_bytes(), "image/png"

    def _read_record_locked(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if isinstance(loaded, dict):
            return loaded
        return None

    @staticmethod
    def _public_summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_id": str(record.get("artifact_id") or ""),
            "created_at": str(record.get("created_at") or ""),
            "control_type": str(record.get("control_type") or ""),
            "status": str(record.get("status") or ""),
            "dangerous": bool(record.get("dangerous", False)),
            "goal": str(record.get("goal") or ""),
            "platform": str(record.get("platform") or ""),
            "transport": str(record.get("transport") or ""),
            "output_preview": str(record.get("output_preview") or ""),
            "action_type": str(record.get("action_type") or ""),
            "target": str(record.get("target") or ""),
            "model": str(record.get("model") or ""),
            "model_id": str(record.get("model_id") or ""),
            "preview_available": bool(record.get("preview_available", False)),
            "preview_path": str(record.get("preview_path") or ""),
            "detail_path": str(record.get("detail_path") or ""),
        }

    @classmethod
    def _public_record(cls, record: dict[str, Any]) -> dict[str, Any]:
        payload = cls._public_summary(record)
        payload["output"] = str(record.get("output") or "")
        if isinstance(record.get("action"), dict):
            payload["action"] = _json_safe(record.get("action"))
        if isinstance(record.get("data"), dict):
            payload["data"] = _json_safe(record.get("data"))
        if isinstance(record.get("metadata"), dict):
            payload["metadata"] = _json_safe(record.get("metadata"))
        return payload
