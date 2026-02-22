import time
import unittest
from pathlib import Path
import tempfile

from novaadapt_core.job_store import JobStore
from novaadapt_core.jobs import JobManager


class JobManagerTests(unittest.TestCase):
    def test_submit_and_get_success(self):
        jobs = JobManager(max_workers=1)

        def work(value: int):
            return {"value": value * 2}

        job_id = jobs.submit(work, 21)

        record = None
        for _ in range(50):
            record = jobs.get(job_id)
            if record and record["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)

        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["result"], {"value": 42})
        jobs.shutdown()

    def test_failed_job(self):
        jobs = JobManager(max_workers=1)

        def work():
            raise RuntimeError("boom")

        job_id = jobs.submit(work)

        record = None
        for _ in range(50):
            record = jobs.get(job_id)
            if record and record["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)

        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "failed")
        self.assertIn("boom", record["error"])
        jobs.shutdown()

    def test_cancel_queued_job(self):
        jobs = JobManager(max_workers=1)

        def slow_work():
            time.sleep(0.2)
            return {"status": "done"}

        first = jobs.submit(slow_work)
        second = jobs.submit(slow_work)

        canceled = jobs.cancel(second)
        self.assertIsNotNone(canceled)
        self.assertTrue(canceled["canceled"])
        self.assertEqual(canceled["status"], "canceled")

        record = jobs.get(second)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "canceled")
        self.assertTrue(record["cancel_requested"])

        # Allow first job to complete cleanly before shutdown.
        for _ in range(50):
            first_record = jobs.get(first)
            if first_record and first_record["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        jobs.shutdown()

    def test_persists_records_with_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.db")
            jobs = JobManager(max_workers=1, store=store)

            def work():
                return {"ok": True}

            job_id = jobs.submit(work)
            for _ in range(50):
                record = jobs.get(job_id)
                if record and record["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.01)
            jobs.shutdown()

            # Simulate restart: new manager can still list/get persisted jobs.
            jobs2 = JobManager(max_workers=1, store=store)
            persisted = jobs2.get(job_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted["status"], "succeeded")
            self.assertEqual(persisted["result"], {"ok": True})
            self.assertGreaterEqual(len(jobs2.list(limit=10)), 1)
            jobs2.shutdown()


if __name__ == "__main__":
    unittest.main()
