import tempfile
import unittest
from pathlib import Path

from novaadapt_core.job_store import JobStore


class JobStoreTests(unittest.TestCase):
    def test_upsert_get_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "jobs.db"
            store = JobStore(db)

            record = {
                "id": "job-1",
                "status": "queued",
                "created_at": "2026-01-01T00:00:00Z",
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
                "cancel_requested": False,
            }
            store.upsert(record)

            fetched = store.get("job-1")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["status"], "queued")

            record["status"] = "succeeded"
            record["result"] = {"ok": True}
            store.upsert(record)

            fetched = store.get("job-1")
            self.assertEqual(fetched["status"], "succeeded")
            self.assertEqual(fetched["result"], {"ok": True})

            listed = store.list(limit=5)
            self.assertEqual(len(listed), 1)


if __name__ == "__main__":
    unittest.main()
