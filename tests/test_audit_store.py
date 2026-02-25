import tempfile
import unittest
from pathlib import Path
import sqlite3

from novaadapt_core.audit_store import AuditStore


class AuditStoreTests(unittest.TestCase):
    def test_append_and_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(Path(tmp) / "events.db")

            e1 = store.append(
                category="run",
                action="run_async",
                status="ok",
                entity_type="job",
                entity_id="job-1",
                payload={"job_id": "job-1"},
            )
            e2 = store.append(
                category="plans",
                action="approve",
                status="failed",
                entity_type="plan",
                entity_id="plan-1",
                payload={"id": "plan-1"},
            )

            all_events = store.list(limit=10)
            self.assertEqual(len(all_events), 2)
            self.assertEqual(all_events[0]["id"], e2["id"])

            run_events = store.list(limit=10, category="run")
            self.assertEqual(len(run_events), 1)
            self.assertEqual(run_events[0]["entity_id"], "job-1")

            plan_events = store.list(limit=10, entity_type="plan", entity_id="plan-1")
            self.assertEqual(len(plan_events), 1)
            self.assertEqual(plan_events[0]["action"], "approve")

            since = store.list(limit=10, since_id=e1["id"])
            self.assertEqual(len(since), 1)
            self.assertEqual(since[0]["id"], e2["id"])

    def test_append_retries_transient_operational_error(self):
        class FlakyAuditStore(AuditStore):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._append_attempts = 0

            def _append_once(self, **kwargs):  # type: ignore[override]
                self._append_attempts += 1
                if self._append_attempts == 1:
                    raise sqlite3.OperationalError("disk I/O error")
                return super()._append_once(**kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            store = FlakyAuditStore(Path(tmp) / "events.db", retry_attempts=3, retry_backoff_seconds=0)
            item = store.append(category="run", action="run", status="ok")
            self.assertEqual(item["category"], "run")
            self.assertEqual(store._append_attempts, 2)


if __name__ == "__main__":
    unittest.main()
