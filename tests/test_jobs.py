import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
