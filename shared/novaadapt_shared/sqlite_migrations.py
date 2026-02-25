from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


@dataclass(frozen=True)
class SQLiteMigration:
    migration_id: str
    statements: tuple[str, ...]


def apply_sqlite_migrations(conn, migrations: Iterable[SQLiteMigration]) -> list[str]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied_rows = conn.execute("SELECT migration_id FROM schema_migrations").fetchall()
    applied = {str(row[0]) for row in applied_rows}
    newly_applied: list[str] = []
    applied_at = _now_iso()
    for migration in migrations:
        if migration.migration_id in applied:
            continue
        for statement in migration.statements:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations(migration_id, applied_at) VALUES (?, ?)",
            (migration.migration_id, applied_at),
        )
        newly_applied.append(migration.migration_id)
    conn.commit()
    return newly_applied


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
