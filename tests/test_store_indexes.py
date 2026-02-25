import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from novaadapt_core.audit_store import AuditStore
from novaadapt_core.idempotency_store import IdempotencyStore
from novaadapt_core.job_store import JobStore
from novaadapt_core.plan_store import PlanStore
from novaadapt_shared.undo_queue import UndoQueue


def _index_names(db_path: Path, table: str) -> set[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    return {str(row[1]) for row in rows}


class StoreIndexTests(unittest.TestCase):
    def test_audit_store_creates_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "events.db"
            AuditStore(db)
            names = _index_names(db, "audit_events")
            self.assertIn("idx_audit_events_category_id", names)
            self.assertIn("idx_audit_events_entity_type_entity_id_id", names)
            self.assertIn("idx_audit_events_created_at", names)

    def test_idempotency_store_creates_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "idempotency.db"
            IdempotencyStore(db)
            names = _index_names(db, "idempotency_entries")
            self.assertIn("idx_idempotency_entries_updated_at", names)

    def test_job_store_creates_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "jobs.db"
            JobStore(db)
            names = _index_names(db, "async_jobs")
            self.assertIn("idx_async_jobs_created_at", names)
            self.assertIn("idx_async_jobs_status_finished_at", names)

    def test_plan_store_creates_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "plans.db"
            PlanStore(db)
            names = _index_names(db, "plans")
            self.assertIn("idx_plans_created_at", names)
            self.assertIn("idx_plans_status_updated_at", names)

    def test_undo_queue_creates_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "actions.db"
            UndoQueue(db)
            names = _index_names(db, "action_log")
            self.assertIn("idx_action_log_undone_id", names)
            self.assertIn("idx_action_log_created_at", names)


if __name__ == "__main__":
    unittest.main()
