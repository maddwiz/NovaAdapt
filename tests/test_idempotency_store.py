import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
