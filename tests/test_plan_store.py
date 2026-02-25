import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
