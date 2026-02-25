import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import sqlite3

from novaadapt_shared.undo_queue import UndoQueue


class UndoQueueTests(unittest.TestCase):
    def test_records_and_retrieves_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = UndoQueue(db_path=Path(tmp) / "actions.db")
            row_id = queue.record(
                action={"type": "click", "target": "OK"},
                status="ok",
                undo_action={"type": "hotkey", "target": "cmd+z"},
            )

            row = queue.get(row_id)
            self.assertIsNotNone(row)
            self.assertEqual(row["action"]["type"], "click")
            self.assertEqual(row["undo_action"]["type"], "hotkey")

    def test_latest_pending_and_mark_undone(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = UndoQueue(db_path=Path(tmp) / "actions.db")
            first = queue.record(action={"type": "click", "target": "A"}, status="ok")
            second = queue.record(action={"type": "click", "target": "B"}, status="ok")

            latest = queue.latest_pending()
            self.assertEqual(latest["id"], second)

            changed = queue.mark_undone(second)
            self.assertTrue(changed)
            self.assertTrue(queue.get(second)["undone"])

            next_latest = queue.latest_pending()
            self.assertEqual(next_latest["id"], first)

    def test_prune_older_than_removes_stale_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "actions.db"
            queue = UndoQueue(db_path=db)
            stale = queue.record(action={"type": "click", "target": "A"}, status="ok")
            fresh = queue.record(action={"type": "click", "target": "B"}, status="ok")

            with closing(sqlite3.connect(db)) as conn:
                conn.execute("UPDATE action_log SET created_at = '2000-01-01 00:00:00' WHERE id = ?", (stale,))
                conn.commit()

            removed = queue.prune_older_than(older_than_seconds=1)
            self.assertEqual(removed, 1)
            self.assertIsNone(queue.get(stale))
            self.assertIsNotNone(queue.get(fresh))


if __name__ == "__main__":
    unittest.main()
