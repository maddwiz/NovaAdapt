import unittest

from vibe.vibe_terminal import _submit_and_optionally_wait


class _StubClient:
    def __init__(self):
        self._job_calls = 0
        self.last_run_async = None

    def run_async(self, objective, idempotency_key=None):
        self.last_run_async = {
            "objective": objective,
            "idempotency_key": idempotency_key,
        }
        return {"job_id": "job-1", "status": "queued"}

    def job(self, job_id):
        self._job_calls += 1
        if self._job_calls < 3:
            return {"id": job_id, "status": "running"}
        return {"id": job_id, "status": "succeeded"}


class VibeTerminalTests(unittest.TestCase):
    def test_submit_without_wait(self):
        client = _StubClient()
        out = _submit_and_optionally_wait(
            client=client,
            objective="build dashboard",
            wait=False,
            poll_interval=0.01,
            idempotency_prefix="testvibe",
        )
        self.assertEqual(out["objective"], "build dashboard")
        self.assertEqual(out["submitted"]["job_id"], "job-1")
        self.assertNotIn("job", out)
        self.assertTrue(client.last_run_async["idempotency_key"].startswith("testvibe-"))

    def test_submit_with_wait_until_terminal_state(self):
        client = _StubClient()
        out = _submit_and_optionally_wait(
            client=client,
            objective="run checks",
            wait=True,
            poll_interval=0.001,
            idempotency_prefix="testvibe",
        )
        self.assertEqual(out["job"]["status"], "succeeded")
        self.assertGreaterEqual(client._job_calls, 3)

    def test_submit_rejects_empty_objective(self):
        client = _StubClient()
        with self.assertRaises(ValueError):
            _submit_and_optionally_wait(
                client=client,
                objective=" ",
                wait=False,
                poll_interval=0.01,
                idempotency_prefix="testvibe",
            )


if __name__ == "__main__":
    unittest.main()
