import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import sqlite3

from novaadapt_core.plan_store import PlanStore


class PlanStoreTests(unittest.TestCase):
    def test_create_list_get_approve_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PlanStore(Path(tmp) / "plans.db")

            created = store.create(
                {
                    "objective": "click ok",
                    "strategy": "single",
                    "model": "local",
                    "model_id": "qwen",
                    "actions": [{"type": "click", "target": "OK"}],
                    "votes": {},
                    "model_errors": {},
                    "attempted_models": ["local"],
                }
            )
            self.assertEqual(created["status"], "pending")
            self.assertEqual(created["objective"], "click ok")

            listed = store.list(limit=10)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], created["id"])

            fetched = store.get(created["id"])
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["model"], "local")
            self.assertEqual(fetched["progress_completed"], 0)
            self.assertEqual(fetched["progress_total"], 1)

            executing = store.mark_executing(created["id"], total_actions=1)
            self.assertIsNotNone(executing)
            self.assertEqual(executing["status"], "executing")

            progress = store.update_execution_progress(
                created["id"],
                execution_results=[{"status": "ok"}],
                action_log_ids=[1],
                progress_completed=1,
                progress_total=1,
            )
            self.assertIsNotNone(progress)
            self.assertEqual(progress["progress_completed"], 1)
            self.assertEqual(progress["progress_total"], 1)

            approved = store.approve(
                created["id"],
                execution_results=[{"status": "ok"}],
                action_log_ids=[1],
                status="executed",
            )
            self.assertIsNotNone(approved)
            self.assertEqual(approved["status"], "executed")
            self.assertEqual(approved["execution_results"][0]["status"], "ok")
            self.assertEqual(approved["action_log_ids"][0], 1)
            self.assertIsNone(approved["execution_error"])

            created_2 = store.create({"objective": "do not run", "actions": []})
            rejected = store.reject(created_2["id"], reason="unsafe")
            self.assertIsNotNone(rejected)
            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(rejected["reject_reason"], "unsafe")

            created_3 = store.create({"objective": "fails", "actions": [{"type": "click", "target": "X"}]})
            failed = store.fail_execution(created_3["id"], error="boom", progress_completed=0, progress_total=1)
            self.assertIsNotNone(failed)
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["execution_error"], "boom")

    def test_prune_older_than_only_removes_terminal_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PlanStore(Path(tmp) / "plans.db")

            old_terminal = store.create({"objective": "old done", "actions": []})
            old_active = store.create({"objective": "old active", "actions": []})
            store.approve(old_terminal["id"], execution_results=[], action_log_ids=[], status="executed")

            # Force both plans to look stale; prune must only remove terminal statuses.
            with closing(sqlite3.connect(store.db_path)) as conn:
                conn.execute(
                    "UPDATE plans SET updated_at = '2000-01-01T00:00:00+00:00' WHERE id IN (?, ?)",
                    (old_terminal["id"], old_active["id"]),
                )
                conn.commit()

            removed = store.prune_older_than(older_than_seconds=1)
            self.assertEqual(removed, 1)
            self.assertIsNone(store.get(old_terminal["id"]))
            self.assertIsNotNone(store.get(old_active["id"]))


if __name__ == "__main__":
    unittest.main()
