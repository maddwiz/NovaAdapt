import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from novaadapt_core import cli


class _StubAPIClient:
    instances: list["_StubAPIClient"] = []

    def __init__(
        self,
        base_url,
        token,
        timeout_seconds,
        max_retries=2,
        retry_backoff_seconds=0.2,
    ):
        self.base_url = base_url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.issue_kwargs = None
        self.added_device_id = None
        self.revoked_token = None
        self.last_run_async = None
        self.last_create_plan = None
        self._job_calls = 0
        self._plan_calls = 0
        _StubAPIClient.instances.append(self)

    def add_allowed_device(self, device_id):
        self.added_device_id = device_id
        return {"status": "ok", "added": True, "device_id": device_id}

    def issue_session_token(self, **kwargs):
        self.issue_kwargs = kwargs
        return {
            "token": "na1.session",
            "session_id": "sess-1",
            "subject": kwargs.get("subject"),
            "scopes": kwargs.get("scopes"),
            "device_id": kwargs.get("device_id"),
            "expires_at": 1234567890,
        }

    def revoke_session_token(self, token):
        self.revoked_token = token
        return {"status": "ok", "revoked": True}

    def run_async(self, idempotency_key=None, **kwargs):
        self.last_run_async = {"idempotency_key": idempotency_key, **kwargs}
        return {"job_id": "job-1", "status": "queued"}

    def create_plan(self, idempotency_key=None, **kwargs):
        self.last_create_plan = {"idempotency_key": idempotency_key, **kwargs}
        return {"id": "plan-1", "status": "pending"}

    def job(self, job_id):
        self._job_calls += 1
        if self._job_calls < 2:
            return {"id": job_id, "status": "running"}
        return {"id": job_id, "status": "succeeded"}

    def plan(self, plan_id):
        self._plan_calls += 1
        if self._plan_calls < 2:
            return {"id": plan_id, "status": "pending"}
        return {"id": plan_id, "status": "executed"}


class XRealCLITests(unittest.TestCase):
    def setUp(self):
        _StubAPIClient.instances = []

    def _run_cli(self, *argv: str):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["novaadapt", *argv]), redirect_stdout(stdout):
            cli.main()
        raw = stdout.getvalue().strip()
        if not raw:
            return None
        return json.loads(raw)

    @mock.patch("novaadapt_core.cli.NovaAdaptAPIClient", _StubAPIClient)
    def test_xreal_intent_with_admin_session_wait(self):
        payload = self._run_cli(
            "xreal-intent",
            "--bridge-url",
            "http://127.0.0.1:9797",
            "--admin-token",
            "admin-token",
            "--ensure-device-allowlisted",
            "--session-device-id",
            "xreal-x1-1",
            "--session-scopes",
            "read,run",
            "--objective",
            "Open dashboard",
            "--display-mode",
            "anchor",
            "--hand-tracking",
            "--firmware-version",
            "2.1.0",
            "--wait",
            "--poll-interval",
            "0.001",
        )

        admin_client = _StubAPIClient.instances[0]
        runtime_client = _StubAPIClient.instances[1]
        self.assertEqual(admin_client.token, "admin-token")
        self.assertEqual(runtime_client.token, "na1.session")
        self.assertEqual(admin_client.added_device_id, "xreal-x1-1")
        self.assertEqual(admin_client.issue_kwargs["scopes"], ["read", "run"])
        self.assertEqual(admin_client.revoked_token, "na1.session")
        self.assertEqual(runtime_client.last_run_async["metadata"]["wearable_family"], "xreal")
        self.assertEqual(runtime_client.last_run_async["metadata"]["display_mode"], "anchor")
        self.assertEqual(runtime_client.last_run_async["metadata"]["firmware_version"], "2.1.0")
        self.assertTrue(runtime_client.last_run_async["metadata"]["hand_tracking"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["submission_mode"], "run_async")
        self.assertEqual(payload["job"]["status"], "succeeded")
        self.assertEqual(payload["session"]["session_id"], "sess-1")

    @mock.patch("novaadapt_core.cli.NovaAdaptAPIClient", _StubAPIClient)
    def test_xreal_intent_with_direct_token_plan_mode(self):
        payload = self._run_cli(
            "xreal-intent",
            "--core-url",
            "http://127.0.0.1:8787",
            "--token",
            "core-token",
            "--submission-mode",
            "plan",
            "--objective",
            "Draft patrol route",
            "--wait",
            "--poll-interval",
            "0.001",
        )
        runtime_client = _StubAPIClient.instances[0]
        self.assertEqual(runtime_client.token, "core-token")
        self.assertEqual(runtime_client.last_create_plan["objective"], "Draft patrol route")
        self.assertEqual(payload["submission_mode"], "plan")
        self.assertEqual(payload["plan"]["status"], "executed")
        self.assertNotIn("session", payload)

    @mock.patch("novaadapt_core.cli.NovaAdaptAPIClient", _StubAPIClient)
    def test_xreal_intent_requires_token_or_admin_token(self):
        with mock.patch.object(
            sys,
            "argv",
            [
                "novaadapt",
                "xreal-intent",
                "--bridge-url",
                "http://127.0.0.1:9797",
                "--token",
                "",
                "--admin-token",
                "",
                "--objective",
                "Open dashboard",
            ],
        ):
            with self.assertRaises(SystemExit) as exc:
                cli.main()
        self.assertIn("either --token or --admin-token is required", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
