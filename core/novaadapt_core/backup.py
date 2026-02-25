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


def restore_sqlite_db(
    source_backup: Path,
    destination: Path,
    *,
    archive_dir: Path | None = None,
    archive_suffix: str | None = None,
) -> dict[str, Any]:
    source_path = Path(source_backup).expanduser()
    destination_path = Path(destination).expanduser()
    if not source_path.exists():
        return {
            "source": str(source_path),
            "destination": str(destination_path),
            "status": "missing",
            "bytes": 0,
            "previous_backup": None,
        }

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    previous_backup: str | None = None
    if destination_path.exists() and archive_dir is not None:
        archive_root = Path(archive_dir).expanduser()
        archive_root.mkdir(parents=True, exist_ok=True)
        suffix = archive_suffix or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_file = archive_root / f"{destination_path.stem}-pre-restore-{suffix}.db"
        archived = backup_sqlite_db(destination_path, archive_file)
        if archived["status"] == "ok":
            previous_backup = str(archive_file)

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
        "destination": str(destination_path),
        "status": "ok",
        "bytes": int(destination_path.stat().st_size),
        "previous_backup": previous_backup,
    }


def _discover_latest_timestamp(backups_dir: Path, database_names: list[str]) -> str:
    latest: str | None = None
    for name in database_names:
        pattern = f"{name}-*.db"
        for candidate in backups_dir.glob(pattern):
            stem = candidate.stem
            if not stem.startswith(f"{name}-"):
                continue
            timestamp = stem[len(name) + 1 :]
            if latest is None or timestamp > latest:
                latest = timestamp
    if latest is None:
        raise ValueError(f"No backup snapshots found in {backups_dir}")
    return latest


def restore_databases(
    *,
    backups_dir: Path,
    databases: dict[str, Path],
    timestamp: str | None = None,
    archive_dir: Path | None = None,
) -> dict[str, Any]:
    source_dir = Path(backups_dir).expanduser().resolve()
    if not source_dir.exists():
        raise ValueError(f"Backup directory not found: {source_dir}")

    ts = timestamp or _discover_latest_timestamp(source_dir, list(databases.keys()))
    archive_root = (
        Path(archive_dir).expanduser().resolve()
        if archive_dir is not None
        else (source_dir / "pre-restore" / ts).resolve()
    )

    results: dict[str, Any] = {}
    restored = 0
    missing = 0
    for name, destination in databases.items():
        source_file = source_dir / f"{name}-{ts}.db"
        entry = restore_sqlite_db(
            source_file,
            Path(destination),
            archive_dir=archive_root,
            archive_suffix=ts,
        )
        results[name] = entry
        if entry["status"] == "ok":
            restored += 1
        else:
            missing += 1
    return {
        "ok": missing == 0,
        "backups_dir": str(source_dir),
        "archive_dir": str(archive_root),
        "timestamp": ts,
        "restored": restored,
        "missing": missing,
        "databases": results,
    }
