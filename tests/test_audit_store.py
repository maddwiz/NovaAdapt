import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
