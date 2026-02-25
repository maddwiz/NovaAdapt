import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from novaadapt_shared.api_client import APIClientError, NovaAdaptAPIClient


class _Handler(BaseHTTPRequestHandler):
    models_attempts = 0

    def do_GET(self):
        auth = self.headers.get("Authorization")
        if self.path != "/health" and auth != "Bearer token":
            self._send(401, {"error": "unauthorized"})
            return

        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        if self.path == "/openapi.json":
            self._send(200, {"openapi": "3.1.0", "paths": {"/run": {}}})
            return
        if self.path.startswith("/dashboard/data"):
            self._send(
                200,
                {
                    "health": {"ok": True, "service": "novaadapt"},
                    "models_count": 1,
                    "plans": [{"id": "plan-1", "status": "pending"}],
                    "jobs": [{"id": "job-1", "status": "queued"}],
                    "events": [{"id": 1, "category": "run", "action": "run_async"}],
                    "metrics": {"novaadapt_core_requests_total": 1},
                },
            )
            return
        if self.path == "/models":
            _Handler.models_attempts += 1
            if _Handler.models_attempts == 1:
                self._send(502, {"error": "temporary upstream"})
                return
            self._send(200, [{"name": "local"}])
            return
        if self.path == "/jobs/job-1/stream?timeout=2&interval=0.1":
            body = (
                'event: job\n'
                'data: {"id":"job-1","status":"running"}\n\n'
                'event: end\n'
                'data: {"id":"job-1","status":"succeeded"}\n\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/plans/plan-1/stream?timeout=2&interval=0.1":
            body = (
                'event: plan\n'
                'data: {"id":"plan-1","status":"pending"}\n\n'
                'event: end\n'
                'data: {"id":"plan-1","status":"executed"}\n\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/events/stream?timeout=2&interval=0.1&since_id=0":
            body = (
                'event: audit\n'
                'data: {"id":1,"category":"run","action":"run_async"}\n\n'
                'event: timeout\n'
                'data: {"request_id":"rid"}\n\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/jobs/"):
            self._send(200, {"id": "job-1", "status": "succeeded"})
            return
        if self.path.startswith("/jobs"):
            self._send(200, [{"id": "job-1"}])
            return
        if self.path.startswith("/plans/"):
            self._send(200, {"id": "plan-1", "status": "pending"})
            return
        if self.path.startswith("/plans"):
            self._send(200, [{"id": "plan-1", "status": "pending"}])
            return
        if self.path.startswith("/history"):
            self._send(200, [{"id": 1}])
            return
        if self.path.startswith("/events"):
            self._send(200, [{"id": 1, "category": "run", "action": "run_async"}])
            return
        if self.path == "/metrics":
            body = "novaadapt_core_requests_total 1\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self._send(404, {"error": "not found"})

    def do_POST(self):
        auth = self.headers.get("Authorization")
        if auth != "Bearer token":
            self._send(401, {"error": "unauthorized"})
            return

        if self.path in {
            "/run",
            "/run_async",
            "/undo",
            "/check",
            "/auth/session",
            "/auth/session/revoke",
            "/jobs/job-1/cancel",
            "/plans",
            "/plans/plan-1/approve",
            "/plans/plan-1/approve_async",
            "/plans/plan-1/reject",
            "/plans/plan-1/undo",
        }:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)
            if self.path == "/run":
                self._send(
                    200,
                    {
                        "status": "ok",
                        "objective": payload.get("objective"),
                        "idempotency": self.headers.get("Idempotency-Key"),
                    },
                )
            elif self.path == "/run_async":
                self._send(202, {"job_id": "job-1", "status": "queued"})
            elif self.path == "/jobs/job-1/cancel":
                self._send(200, {"id": "job-1", "status": "canceled", "canceled": True})
            elif self.path == "/plans":
                self._send(201, {"id": "plan-1", "status": "pending"})
            elif self.path == "/plans/plan-1/approve":
                self._send(200, {"id": "plan-1", "status": "executed"})
            elif self.path == "/plans/plan-1/approve_async":
                self._send(202, {"job_id": "job-plan-1", "status": "queued", "kind": "plan_approval"})
            elif self.path == "/plans/plan-1/reject":
                self._send(200, {"id": "plan-1", "status": "rejected"})
            elif self.path == "/plans/plan-1/undo":
                self._send(200, {"plan_id": "plan-1", "results": [{"id": 1, "ok": True}]})
            elif self.path == "/undo":
                self._send(200, {"id": payload.get("id", 1), "status": "marked_undone"})
            elif self.path == "/auth/session":
                self._send(
                    200,
                    {
                        "token": "na1.mock-session",
                        "session_id": "session-1",
                        "subject": payload.get("subject", "bridge-session"),
                        "scopes": payload.get("scopes", ["read"]),
                        "device_id": payload.get("device_id", ""),
                        "expires_at": 9999999999,
                        "issued_at": 9999999000,
                    },
                )
            elif self.path == "/auth/session/revoke":
                self._send(
                    200,
                    {
                        "revoked": True,
                        "already_revoked": False,
                        "session_id": "session-1",
                        "expires_at": 9999999999,
                    },
                )
            else:
                self._send(200, [{"name": "local", "ok": True}])
            return

        self._send(404, {"error": "not found"})

    def _send(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class APIClientTests(unittest.TestCase):
    def setUp(self):
        _Handler.models_attempts = 0
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.host, self.port = self.server.server_address
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_core_operations(self):
        client = NovaAdaptAPIClient(base_url=f"http://{self.host}:{self.port}", token="token")

        self.assertTrue(client.health()["ok"])
        self.assertEqual(client.openapi()["openapi"], "3.1.0")
        self.assertEqual(client.dashboard_data()["models_count"], 1)
        self.assertEqual(client.models()[0]["name"], "local")
        self.assertEqual(client.run("demo", idempotency_key="idem-1")["idempotency"], "idem-1")
        self.assertEqual(client.run_async("demo")["status"], "queued")
        self.assertEqual(client.jobs(limit=5)[0]["id"], "job-1")
        self.assertEqual(client.job("job-1")["status"], "succeeded")
        stream_events = client.job_stream("job-1", timeout_seconds=2, interval_seconds=0.1)
        self.assertEqual(stream_events[0]["event"], "job")
        self.assertEqual(stream_events[-1]["data"]["status"], "succeeded")
        self.assertTrue(client.cancel_job("job-1")["canceled"])
        self.assertEqual(client.create_plan("demo")["id"], "plan-1")
        self.assertEqual(client.plans(limit=3)[0]["id"], "plan-1")
        self.assertEqual(client.plan("plan-1")["status"], "pending")
        self.assertEqual(client.approve_plan("plan-1", execute=True)["status"], "executed")
        self.assertEqual(client.retry_failed_plan("plan-1")["status"], "executed")
        self.assertEqual(client.approve_plan_async("plan-1", execute=True)["kind"], "plan_approval")
        self.assertEqual(client.reject_plan("plan-1", reason="nope")["status"], "rejected")
        self.assertEqual(client.undo_plan("plan-1", mark_only=True)["plan_id"], "plan-1")
        plan_events = client.plan_stream("plan-1", timeout_seconds=2, interval_seconds=0.1)
        self.assertEqual(plan_events[0]["event"], "plan")
        self.assertEqual(plan_events[-1]["data"]["status"], "executed")
        self.assertEqual(client.history(limit=1)[0]["id"], 1)
        self.assertEqual(client.events(limit=10)[0]["category"], "run")
        self.assertEqual(client.events_stream(timeout_seconds=2, interval_seconds=0.1, since_id=0)[0]["event"], "audit")
        self.assertEqual(client.undo(id=1, mark_only=True)["status"], "marked_undone")
        session_payload = client.issue_session_token(
            scopes=["read", "run"],
            subject="iphone-operator",
            device_id="iphone-1",
            ttl_seconds=300,
        )
        self.assertEqual(session_payload["token"], "na1.mock-session")
        self.assertEqual(session_payload["session_id"], "session-1")
        revoke_payload = client.revoke_session_token("na1.mock-session")
        self.assertTrue(revoke_payload["revoked"])
        revoke_by_id_payload = client.revoke_session_id("session-1", expires_at=9999999999)
        self.assertTrue(revoke_by_id_payload["revoked"])
        self.assertIn("novaadapt_core_requests_total", client.metrics_text())

    def test_error_without_token(self):
        client = NovaAdaptAPIClient(base_url=f"http://{self.host}:{self.port}")
        with self.assertRaises(APIClientError):
            client.models()
        with self.assertRaises(APIClientError):
            client.revoke_session()

    def test_retry_for_transient_http(self):
        client = NovaAdaptAPIClient(
            base_url=f"http://{self.host}:{self.port}",
            token="token",
            max_retries=2,
            retry_backoff_seconds=0,
        )
        models = client.models()
        self.assertEqual(models[0]["name"], "local")
        self.assertGreaterEqual(_Handler.models_attempts, 2)


if __name__ == "__main__":
    unittest.main()
