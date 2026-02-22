import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
