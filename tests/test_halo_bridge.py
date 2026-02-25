import unittest
from unittest import mock

from novaadapt_shared import APIClientError
from wearables.halo_bridge import (
    HaloIntent,
    _build_runtime_client,
    _clamp_confidence,
    _parse_scopes,
    _submit_intent,
)


class _StubClient:
    def __init__(self):
        self.job_calls = 0
        self.plan_calls = 0
        self.last_run_async = None
        self.last_create_plan = None

    def run_async(self, idempotency_key=None, **kwargs):
        self.last_run_async = {"idempotency_key": idempotency_key, **kwargs}
        return {"job_id": "job-1", "status": "queued"}

    def create_plan(self, idempotency_key=None, **kwargs):
        self.last_create_plan = {"idempotency_key": idempotency_key, **kwargs}
        return {"id": "plan-1", "status": "pending"}

    def job(self, job_id):
        self.job_calls += 1
        if self.job_calls < 3:
            return {"id": job_id, "status": "running"}
        return {"id": job_id, "status": "succeeded"}

    def plan(self, plan_id):
        self.plan_calls += 1
        if self.plan_calls < 2:
            return {"id": plan_id, "status": "pending"}
        return {"id": plan_id, "status": "executed"}


class _RunningForeverClient(_StubClient):
    def job(self, job_id):
        self.job_calls += 1
        return {"id": job_id, "status": "running"}


class _StubAPIClient:
    instances: list["_StubAPIClient"] = []
    issued_payload: dict = {"token": "na1.session", "session_id": "sess-1"}

    def __init__(self, base_url, token, timeout_seconds, max_retries, retry_backoff_seconds):
        self.base_url = base_url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        _StubAPIClient.instances.append(self)

    def issue_session_token(self, **kwargs):
        self.issue_kwargs = kwargs
        return dict(_StubAPIClient.issued_payload)


class HaloBridgeTests(unittest.TestCase):
    def setUp(self):
        _StubAPIClient.instances = []
        _StubAPIClient.issued_payload = {"token": "na1.session", "session_id": "sess-1"}

    def test_submit_run_async_without_wait(self):
        client = _StubClient()
        out = _submit_intent(
            client=client,
            intent=HaloIntent(transcript="open dashboard", confidence=0.9),
            submission_mode="run_async",
            wait=False,
            wait_timeout_seconds=1.0,
            poll_interval_seconds=0.001,
            idempotency_prefix="testhalo",
        )
        self.assertEqual(out["submission_mode"], "run_async")
        self.assertEqual(out["submitted"]["job_id"], "job-1")
        self.assertNotIn("job", out)
        self.assertTrue(client.last_run_async["idempotency_key"].startswith("testhalo-"))

    def test_submit_run_async_waits_for_job(self):
        client = _StubClient()
        out = _submit_intent(
            client=client,
            intent=HaloIntent(transcript="run smoke", confidence=0.9),
            submission_mode="run_async",
            wait=True,
            wait_timeout_seconds=5.0,
            poll_interval_seconds=0.001,
            idempotency_prefix="testhalo",
        )
        self.assertEqual(out["job"]["status"], "succeeded")
        self.assertGreaterEqual(client.job_calls, 3)

    def test_submit_plan_waits_for_plan_state(self):
        client = _StubClient()
        out = _submit_intent(
            client=client,
            intent=HaloIntent(transcript="draft release plan", confidence=0.8),
            submission_mode="plan",
            wait=True,
            wait_timeout_seconds=5.0,
            poll_interval_seconds=0.001,
            idempotency_prefix="testhalo",
        )
        self.assertEqual(out["submission_mode"], "plan")
        self.assertEqual(out["submitted"]["id"], "plan-1")
        self.assertEqual(out["plan"]["status"], "executed")
        self.assertGreaterEqual(client.plan_calls, 2)
        self.assertTrue(client.last_create_plan["idempotency_key"].startswith("testhalo-"))

    def test_submit_run_async_wait_timeout(self):
        client = _RunningForeverClient()
        out = _submit_intent(
            client=client,
            intent=HaloIntent(transcript="long task", confidence=0.7),
            submission_mode="run_async",
            wait=True,
            wait_timeout_seconds=0.05,
            poll_interval_seconds=0.01,
            idempotency_prefix="testhalo",
        )
        self.assertTrue(out["job"]["timeout"])
        self.assertEqual(out["job"]["status"], "running")

    def test_parse_scopes(self):
        self.assertEqual(_parse_scopes("read, run, plan"), ["read", "run", "plan"])
        with self.assertRaises(ValueError):
            _parse_scopes(" , ")

    def test_clamp_confidence(self):
        self.assertEqual(_clamp_confidence(-0.5), 0.0)
        self.assertEqual(_clamp_confidence(1.7), 1.0)
        self.assertAlmostEqual(_clamp_confidence(0.42), 0.42)

    @mock.patch("wearables.halo_bridge.NovaAdaptAPIClient", _StubAPIClient)
    def test_build_runtime_client_with_admin_token_issues_session(self):
        runtime_client, admin_client, leased_token, issued = _build_runtime_client(
            endpoint_url="http://127.0.0.1:9797",
            token=None,
            admin_token="admin-token",
            session_scopes=["read", "run"],
            session_ttl=300,
            session_device_id="halo-1",
            session_subject="halo",
        )
        self.assertEqual(admin_client.token, "admin-token")
        self.assertEqual(runtime_client.token, "na1.session")
        self.assertEqual(leased_token, "na1.session")
        self.assertEqual(issued["session_id"], "sess-1")
        self.assertEqual(admin_client.issue_kwargs["scopes"], ["read", "run"])
        self.assertEqual(admin_client.issue_kwargs["device_id"], "halo-1")

    @mock.patch("wearables.halo_bridge.NovaAdaptAPIClient", _StubAPIClient)
    def test_build_runtime_client_requires_token_without_admin(self):
        with self.assertRaises(ValueError):
            _build_runtime_client(
                endpoint_url="http://127.0.0.1:9797",
                token="",
                admin_token="",
                session_scopes=["read"],
                session_ttl=300,
                session_device_id=None,
                session_subject="halo",
            )

    @mock.patch("wearables.halo_bridge.NovaAdaptAPIClient", _StubAPIClient)
    def test_build_runtime_client_fails_when_session_token_missing(self):
        _StubAPIClient.issued_payload = {"session_id": "sess-1"}
        with self.assertRaises(APIClientError):
            _build_runtime_client(
                endpoint_url="http://127.0.0.1:9797",
                token=None,
                admin_token="admin-token",
                session_scopes=["read"],
                session_ttl=300,
                session_device_id=None,
                session_subject="halo",
            )


if __name__ == "__main__":
    unittest.main()
