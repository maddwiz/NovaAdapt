import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from novaadapt_core.backup import backup_databases, backup_sqlite_db, restore_databases, restore_sqlite_db


def _write_fixture_db(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES (?)", (value,))
        conn.commit()


def _read_fixture_values(path: Path) -> list[str]:
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("SELECT value FROM sample ORDER BY id").fetchall()
    return [str(row[0]) for row in rows]


class BackupTests(unittest.TestCase):
    def test_backup_sqlite_db_copies_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "actions.db"
            dst = Path(tmp) / "snapshots" / "actions-copy.db"
            _write_fixture_db(src, "ok")

            result = backup_sqlite_db(src, dst)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["source"], str(src))
            self.assertEqual(result["backup"], str(dst))
            self.assertGreater(result["bytes"], 0)
            self.assertEqual(_read_fixture_values(dst), ["ok"])

    def test_backup_sqlite_db_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "missing.db"
            dst = Path(tmp) / "snapshots" / "missing-copy.db"

            result = backup_sqlite_db(src, dst)

            self.assertEqual(result["status"], "missing")
            self.assertEqual(result["source"], str(src))
            self.assertIsNone(result["backup"])
            self.assertEqual(result["bytes"], 0)
            self.assertFalse(dst.exists())

    def test_backup_databases_reports_copied_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            actions = Path(tmp) / "actions.db"
            _write_fixture_db(actions, "first")
            missing = Path(tmp) / "plans.db"
            out_dir = Path(tmp) / "backups"

            result = backup_databases(
                out_dir=out_dir,
                databases={
                    "actions": actions,
                    "plans": missing,
                },
                timestamp="20260225T120000Z",
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["out_dir"], str(out_dir.resolve()))
            self.assertEqual(result["timestamp"], "20260225T120000Z")
            self.assertEqual(result["copied"], 1)
            self.assertEqual(result["missing"], 1)

            actions_entry = result["databases"]["actions"]
            self.assertEqual(actions_entry["status"], "ok")
            self.assertEqual(_read_fixture_values(Path(actions_entry["backup"])), ["first"])

            plans_entry = result["databases"]["plans"]
            self.assertEqual(plans_entry["status"], "missing")
            self.assertIsNone(plans_entry["backup"])

    def test_restore_sqlite_db_restores_and_archives_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup_src = Path(tmp) / "backups" / "actions-20260225T120000Z.db"
            destination = Path(tmp) / "state" / "actions.db"
            archive_dir = Path(tmp) / "archive"
            _write_fixture_db(backup_src, "from-backup")
            _write_fixture_db(destination, "old-value")

            result = restore_sqlite_db(
                backup_src,
                destination,
                archive_dir=archive_dir,
                archive_suffix="20260225T120000Z",
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(_read_fixture_values(destination), ["from-backup"])
            self.assertIsNotNone(result["previous_backup"])
            self.assertEqual(_read_fixture_values(Path(result["previous_backup"])), ["old-value"])

    def test_restore_databases_uses_latest_timestamp_when_not_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            backups_dir = Path(tmp) / "backups"
            _write_fixture_db(backups_dir / "actions-20260224T120000Z.db", "old-actions")
            _write_fixture_db(backups_dir / "actions-20260225T120000Z.db", "new-actions")
            _write_fixture_db(backups_dir / "plans-20260225T120000Z.db", "new-plans")

            actions_dst = Path(tmp) / "runtime" / "actions.db"
            plans_dst = Path(tmp) / "runtime" / "plans.db"
            _write_fixture_db(actions_dst, "current-actions")
            _write_fixture_db(plans_dst, "current-plans")

            result = restore_databases(
                backups_dir=backups_dir,
                databases={"actions": actions_dst, "plans": plans_dst},
                timestamp=None,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["timestamp"], "20260225T120000Z")
            self.assertEqual(_read_fixture_values(actions_dst), ["new-actions"])
            self.assertEqual(_read_fixture_values(plans_dst), ["new-plans"])

    def test_restore_databases_reports_missing_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            backups_dir = Path(tmp) / "backups"
            _write_fixture_db(backups_dir / "actions-20260225T120000Z.db", "new-actions")
            actions_dst = Path(tmp) / "runtime" / "actions.db"
            plans_dst = Path(tmp) / "runtime" / "plans.db"

            result = restore_databases(
                backups_dir=backups_dir,
                databases={"actions": actions_dst, "plans": plans_dst},
                timestamp="20260225T120000Z",
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["restored"], 1)
            self.assertEqual(result["missing"], 1)
            self.assertEqual(result["databases"]["plans"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
