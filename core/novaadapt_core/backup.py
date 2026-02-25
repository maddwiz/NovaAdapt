from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def backup_sqlite_db(source: Path, destination: Path) -> dict[str, Any]:
    source_path = Path(source).expanduser()
    destination_path = Path(destination).expanduser()
    if not source_path.exists():
        return {
            "source": str(source_path),
            "backup": None,
            "status": "missing",
            "bytes": 0,
        }

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        destination_path.unlink()
    src_conn = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(destination_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    return {
        "source": str(source_path),
        "backup": str(destination_path),
        "status": "ok",
        "bytes": int(destination_path.stat().st_size),
    }


def backup_databases(
    *,
    out_dir: Path,
    databases: dict[str, Path],
    timestamp: str | None = None,
) -> dict[str, Any]:
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = Path(out_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}
    missing = 0
    copied = 0
    for name, source in databases.items():
        backup_file = target_dir / f"{name}-{ts}.db"
        entry = backup_sqlite_db(Path(source), backup_file)
        results[name] = entry
        if entry["status"] == "missing":
            missing += 1
        else:
            copied += 1
    return {
        "ok": True,
        "out_dir": str(target_dir),
        "timestamp": ts,
        "copied": copied,
        "missing": missing,
        "databases": results,
    }
