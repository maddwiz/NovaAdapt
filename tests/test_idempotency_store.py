import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from novaadapt_core.idempotency_store import IdempotencyStore


class IdempotencyStoreTests(unittest.TestCase):
    def test_begin_complete_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = IdempotencyStore(Path(tmp) / "idempotency.db")

            state, record = store.begin(
                key="key-1",
                method="POST",
                path="/run",
                payload={"objective": "demo"},
            )
            self.assertEqual(state, "new")
            self.assertIsNone(record)

            store.complete(
                key="key-1",
                method="POST",
                path="/run",
                status_code=200,
                payload={"status": "ok"},
            )

            state, record = store.begin(
                key="key-1",
                method="POST",
                path="/run",
                payload={"objective": "demo"},
            )
            self.assertEqual(state, "replay")
            self.assertEqual(record["status_code"], 200)
            self.assertEqual(record["payload"]["status"], "ok")

    def test_conflict_and_in_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = IdempotencyStore(Path(tmp) / "idempotency.db")
            state, _ = store.begin(
                key="key-1",
                method="POST",
                path="/run",
                payload={"objective": "demo"},
            )
            self.assertEqual(state, "new")

            state, record = store.begin(
                key="key-1",
                method="POST",
                path="/run",
                payload={"objective": "demo"},
            )
            self.assertEqual(state, "in_progress")
            self.assertIn("in progress", record["error"])

            state, record = store.begin(
                key="key-1",
                method="POST",
                path="/run",
                payload={"objective": "different"},
            )
            self.assertEqual(state, "conflict")
            self.assertIn("different payload", record["error"])

    def test_cleanup_expires_old_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "idempotency.db"
            store = IdempotencyStore(
                db,
                retention_seconds=1,
                cleanup_interval_seconds=0,
            )
            state, _ = store.begin(
                key="key-1",
                method="POST",
                path="/run",
                payload={"objective": "demo"},
            )
            self.assertEqual(state, "new")
            store.complete(
                key="key-1",
                method="POST",
                path="/run",
                status_code=200,
                payload={"status": "ok"},
            )

            old_timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
            with sqlite3.connect(db) as conn:
                conn.execute(
                    "UPDATE idempotency_entries SET created_at = ?, updated_at = ? WHERE key = ?",
                    (old_timestamp, old_timestamp, "key-1"),
                )
                conn.commit()

            state, _ = store.begin(
                key="key-2",
                method="POST",
                path="/run_async",
                payload={"objective": "demo2"},
            )
            self.assertEqual(state, "new")

            state, _ = store.begin(
                key="key-1",
                method="POST",
                path="/run",
                payload={"objective": "demo"},
            )
            self.assertEqual(state, "new")

    def test_prune_expired_returns_removed_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "idempotency.db"
            store = IdempotencyStore(
                db,
                retention_seconds=1,
                cleanup_interval_seconds=3600,
            )
            state, _ = store.begin(
                key="old-key",
                method="POST",
                path="/run",
                payload={"objective": "demo"},
            )
            self.assertEqual(state, "new")

            old_timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
            with sqlite3.connect(db) as conn:
                conn.execute(
                    "UPDATE idempotency_entries SET created_at = ?, updated_at = ? WHERE key = ?",
                    (old_timestamp, old_timestamp, "old-key"),
                )
                conn.commit()

            removed = store.prune_expired()
            self.assertEqual(removed, 1)


if __name__ == "__main__":
    unittest.main()
