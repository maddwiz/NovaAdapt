from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentTemplateRecord:
    template_id: str
    name: str
    description: str
    objective: str
    strategy: str
    candidates: list[str]
    steps: list[dict[str, Any]]
    metadata: dict[str, Any]
    memory_snapshot: list[dict[str, Any]]
    tags: list[str]
    source: str
    share_token: str
    shared: bool
    created_at: str
    updated_at: str


class AgentTemplateStore:
    def __init__(self, path: str) -> None:
        self.path = str(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_templates (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    candidates_json TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    memory_snapshot_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    share_token TEXT NOT NULL DEFAULT '',
                    shared INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_templates_updated_at ON agent_templates(updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_templates_share_token ON agent_templates(share_token)"
            )
            conn.commit()

    def create_or_update(
        self,
        *,
        name: str,
        description: str = "",
        objective: str,
        strategy: str = "single",
        candidates: list[str] | None = None,
        steps: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        memory_snapshot: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        source: str = "local",
        template_id: str = "",
        share_token: str = "",
        shared: bool = False,
    ) -> AgentTemplateRecord:
        normalized_name = str(name or "").strip()
        normalized_objective = str(objective or "").strip()
        if not normalized_name:
            raise ValueError("'name' is required")
        if not normalized_objective:
            raise ValueError("'objective' is required")

        now = _utc_now()
        normalized_id = str(template_id or "").strip() or f"agtpl-{uuid.uuid4().hex[:16]}"
        existing = self.get(normalized_id)
        created_at = existing.created_at if existing is not None else now
        chosen_share_token = str(share_token or (existing.share_token if existing is not None else "")).strip()
        shared_flag = bool(shared or (existing.shared if existing is not None else False))

        payload = (
            normalized_id,
            normalized_name,
            str(description or "").strip(),
            normalized_objective,
            str(strategy or "single").strip() or "single",
            json.dumps([str(item).strip() for item in (candidates or []) if str(item).strip()], ensure_ascii=True),
            json.dumps([dict(item) for item in (steps or []) if isinstance(item, dict)], ensure_ascii=True),
            json.dumps(dict(metadata or {}), ensure_ascii=True),
            json.dumps([dict(item) for item in (memory_snapshot or []) if isinstance(item, dict)], ensure_ascii=True),
            json.dumps([str(item).strip() for item in (tags or []) if str(item).strip()], ensure_ascii=True),
            str(source or "local").strip() or "local",
            chosen_share_token,
            1 if shared_flag else 0,
            created_at,
            now,
        )

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO agent_templates (
                    template_id,
                    name,
                    description,
                    objective,
                    strategy,
                    candidates_json,
                    steps_json,
                    metadata_json,
                    memory_snapshot_json,
                    tags_json,
                    source,
                    share_token,
                    shared,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(template_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    objective = excluded.objective,
                    strategy = excluded.strategy,
                    candidates_json = excluded.candidates_json,
                    steps_json = excluded.steps_json,
                    metadata_json = excluded.metadata_json,
                    memory_snapshot_json = excluded.memory_snapshot_json,
                    tags_json = excluded.tags_json,
                    source = excluded.source,
                    share_token = excluded.share_token,
                    shared = excluded.shared,
                    updated_at = excluded.updated_at
                """,
                payload,
            )
            conn.commit()
        record = self.get(normalized_id)
        if record is None:
            raise RuntimeError(f"agent template upsert failed: {normalized_id}")
        return record

    def get(self, template_id: str) -> AgentTemplateRecord | None:
        normalized = str(template_id or "").strip()
        if not normalized:
            raise ValueError("'template_id' is required")
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM agent_templates WHERE template_id = ?", (normalized,)).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_share_token(self, share_token: str) -> AgentTemplateRecord | None:
        normalized = str(share_token or "").strip()
        if not normalized:
            raise ValueError("'share_token' is required")
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM agent_templates WHERE share_token = ? AND shared = 1",
                (normalized,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def list(
        self,
        *,
        limit: int = 50,
        source: str = "",
        tag: str = "",
    ) -> list[AgentTemplateRecord]:
        capped = max(1, min(500, int(limit)))
        normalized_source = str(source or "").strip().lower()
        normalized_tag = str(tag or "").strip().lower()
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_templates ORDER BY updated_at DESC LIMIT ?",
                (capped,),
            ).fetchall()
        records = [self._row_to_record(row) for row in rows]
        if normalized_source:
            records = [item for item in records if item.source.lower() == normalized_source]
        if normalized_tag:
            records = [
                item
                for item in records
                if any(str(tag_item).strip().lower() == normalized_tag for tag_item in item.tags)
            ]
        return records[:capped]

    def update_share(self, template_id: str, *, share_token: str, shared: bool) -> AgentTemplateRecord | None:
        current = self.get(template_id)
        if current is None:
            return None
        with closing(self._connect()) as conn:
            conn.execute(
                """
                UPDATE agent_templates
                SET share_token = ?, shared = ?, updated_at = ?
                WHERE template_id = ?
                """,
                (
                    str(share_token or "").strip(),
                    1 if shared else 0,
                    _utc_now(),
                    current.template_id,
                ),
            )
            conn.commit()
        return self.get(current.template_id)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> AgentTemplateRecord:
        return AgentTemplateRecord(
            template_id=str(row["template_id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            objective=str(row["objective"]),
            strategy=str(row["strategy"]),
            candidates=_load_string_list(row["candidates_json"]),
            steps=_load_dict_list(row["steps_json"]),
            metadata=_load_dict(row["metadata_json"]),
            memory_snapshot=_load_dict_list(row["memory_snapshot_json"]),
            tags=_load_string_list(row["tags_json"]),
            source=str(row["source"]),
            share_token=str(row["share_token"]),
            shared=bool(int(row["shared"] or 0)),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


def _load_string_list(raw: object) -> list[str]:
    try:
        value = json.loads(str(raw or "[]"))
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _load_dict_list(raw: object) -> list[dict[str, Any]]:
    try:
        value = json.loads(str(raw or "[]"))
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _load_dict(raw: object) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
