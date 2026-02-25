import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from novaadapt_core.audit_store import AuditStore
from novaadapt_core.cleanup import prune_local_state
from novaadapt_core.idempotency_store import IdempotencyStore
from novaadapt_core.job_store import JobStore
from novaadapt_core.plan_store import PlanStore
from novaadapt_shared.undo_queue import UndoQueue


class CleanupTests(unittest.TestCase):
    def test_prune_local_state_removes_stale_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            actions_db = Path(tmp) / "actions.db"
            plans_db = Path(tmp) / "plans.db"
            jobs_db = Path(tmp) / "jobs.db"
            idempotency_db = Path(tmp) / "idempotency.db"
            audit_db = Path(tmp) / "events.db"

            action_queue = UndoQueue(actions_db)
            stale_action_id = action_queue.record(action={"type": "click", "target": "A"}, status="ok")

            plan_store = PlanStore(plans_db)
            stale_plan = plan_store.create({"objective": "old plan", "actions": []})
            plan_store.approve(stale_plan["id"], execution_results=[], action_log_ids=[], status="executed")

            job_store = JobStore(jobs_db)
            job_store.upsert(
                {
                    "id": "old-job",
                    "status": "succeeded",
                    "created_at": "2000-01-01T00:00:00+00:00",
                    "started_at": "2000-01-01T00:00:01+00:00",
                    "finished_at": "2000-01-01T00:00:02+00:00",
                    "result": {"ok": True},
                    "error": None,
                    "cancel_requested": False,
                }
            )

            idempotency_store = IdempotencyStore(
                idempotency_db,
                retention_seconds=1,
                cleanup_interval_seconds=3600,
            )
            state, _ = idempotency_store.begin(
                key="old-key",
                method="POST",
                path="/run",
                payload={"objective": "old"},
            )
            self.assertEqual(state, "new")

            audit_store = AuditStore(
                audit_db,
                retention_seconds=1,
                cleanup_interval_seconds=3600,
            )
            stale_event = audit_store.append(category="run", action="old", status="ok")

            # Force selected rows to look old enough for retention-based prune.
            with closing(sqlite3.connect(actions_db)) as conn:
                conn.execute("UPDATE action_log SET created_at = '2000-01-01 00:00:00' WHERE id = ?", (stale_action_id,))
                conn.commit()
            with closing(sqlite3.connect(plans_db)) as conn:
                conn.execute(
                    "UPDATE plans SET updated_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                    (stale_plan["id"],),
                )
                conn.commit()
            with closing(sqlite3.connect(idempotency_db)) as conn:
                conn.execute(
                    "UPDATE idempotency_entries SET updated_at = '2000-01-01T00:00:00+00:00' WHERE key = ?",
                    ("old-key",),
                )
                conn.commit()
            with closing(sqlite3.connect(audit_db)) as conn:
                conn.execute(
                    "UPDATE audit_events SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                    (int(stale_event["id"]),),
                )
                conn.commit()

            result = prune_local_state(
                actions_db_path=actions_db,
                plans_db_path=plans_db,
                jobs_db_path=jobs_db,
                idempotency_db_path=idempotency_db,
                audit_db_path=audit_db,
                actions_retention_seconds=1,
                plans_retention_seconds=1,
                jobs_retention_seconds=1,
                idempotency_retention_seconds=1,
                audit_retention_seconds=1,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(result["removed"]["actions"], 1)
            self.assertEqual(result["removed"]["plans"], 1)
            self.assertEqual(result["removed"]["jobs"], 1)
            self.assertEqual(result["removed"]["idempotency"], 1)
            self.assertEqual(result["removed"]["audit"], 1)
            self.assertEqual(result["removed_total"], 5)


if __name__ == "__main__":
    unittest.main()
