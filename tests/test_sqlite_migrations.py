import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from novaadapt_shared.sqlite_migrations import SQLiteMigration, apply_sqlite_migrations


class SQLiteMigrationTests(unittest.TestCase):
    def test_apply_sqlite_migrations_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.db"
            migrations = (
                SQLiteMigration(
                    migration_id="test_0001_create",
                    statements=(
                        "CREATE TABLE IF NOT EXISTS sample (id INTEGER PRIMARY KEY, value TEXT)",
                    ),
                ),
                SQLiteMigration(
                    migration_id="test_0002_index",
                    statements=(
                        "CREATE INDEX IF NOT EXISTS idx_sample_value ON sample(value)",
                    ),
                ),
            )

            with closing(sqlite3.connect(db)) as conn:
                first = apply_sqlite_migrations(conn, migrations)
                second = apply_sqlite_migrations(conn, migrations)
                rows = conn.execute("SELECT migration_id FROM schema_migrations ORDER BY migration_id").fetchall()

            self.assertEqual(first, ["test_0001_create", "test_0002_index"])
            self.assertEqual(second, [])
            self.assertEqual([row[0] for row in rows], ["test_0001_create", "test_0002_index"])


if __name__ == "__main__":
    unittest.main()
