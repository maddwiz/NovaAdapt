import unittest
from unittest import mock

from novaadapt_shared import APIClientError
from vibe.vibe_terminal import _build_runtime_client, _parse_scopes, _submit_and_optionally_wait


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


class VibeTerminalTests(unittest.TestCase):
    def setUp(self):
        _StubAPIClient.instances = []
        _StubAPIClient.issued_payload = {"token": "na1.session", "session_id": "sess-1"}

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

    def test_parse_scopes(self):
        self.assertEqual(_parse_scopes("read, run,plan"), ["read", "run", "plan"])
        with self.assertRaises(ValueError):
            _parse_scopes(" ,  ")

    @mock.patch("vibe.vibe_terminal.NovaAdaptAPIClient", _StubAPIClient)
    def test_build_runtime_client_with_admin_token_issues_session(self):
        runtime_client, admin_client, leased_token, issued = _build_runtime_client(
            bridge_url="http://127.0.0.1:9797",
            token=None,
            admin_token="admin-token",
            session_scopes=["read", "run"],
            session_ttl=300,
            session_device_id="iphone-1",
            session_subject="vibe",
        )
        self.assertEqual(admin_client.token, "admin-token")
        self.assertEqual(runtime_client.token, "na1.session")
        self.assertEqual(leased_token, "na1.session")
        self.assertEqual(issued["session_id"], "sess-1")
        self.assertEqual(admin_client.issue_kwargs["scopes"], ["read", "run"])
        self.assertEqual(admin_client.issue_kwargs["device_id"], "iphone-1")

    @mock.patch("vibe.vibe_terminal.NovaAdaptAPIClient", _StubAPIClient)
    def test_build_runtime_client_requires_token_without_admin(self):
        with self.assertRaises(ValueError):
            _build_runtime_client(
                bridge_url="http://127.0.0.1:9797",
                token="",
                admin_token="",
                session_scopes=["read"],
                session_ttl=300,
                session_device_id=None,
                session_subject="vibe",
            )

    @mock.patch("vibe.vibe_terminal.NovaAdaptAPIClient", _StubAPIClient)
    def test_build_runtime_client_fails_when_session_token_missing(self):
        _StubAPIClient.issued_payload = {"session_id": "sess-1"}
        with self.assertRaises(APIClientError):
            _build_runtime_client(
                bridge_url="http://127.0.0.1:9797",
                token=None,
                admin_token="admin-token",
                session_scopes=["read"],
                session_ttl=300,
                session_device_id=None,
                session_subject="vibe",
            )


if __name__ == "__main__":
    unittest.main()
