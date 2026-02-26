import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib import error

from novaadapt_shared import api_client as api_client_module
from novaadapt_shared.api_client import APIClientError, NovaAdaptAPIClient


class _Handler(BaseHTTPRequestHandler):
    models_attempts = 0
    terminal_session_id = "term-1"
    allowed_devices = set()

    def do_GET(self):
        auth = self.headers.get("Authorization")
        if self.path != "/health" and auth != "Bearer token":
            self._send(401, {"error": "unauthorized"})
            return

        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        if self.path == "/auth/devices":
            devices = sorted(_Handler.allowed_devices)
            self._send(
                200,
                {
                    "enabled": len(devices) > 0,
                    "count": len(devices),
                    "devices": devices,
                },
            )
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
        if self.path == "/plugins":
            self._send(200, [{"name": "novabridge"}, {"name": "novablox"}])
            return
        if self.path == "/plugins/novabridge/health":
            self._send(200, {"plugin": "novabridge", "ok": True})
            return
        if self.path == "/memory/status":
            self._send(200, {"ok": True, "enabled": True, "backend": "novaspine-http"})
            return
        if self.path == "/novaprime/status":
            self._send(200, {"ok": True, "enabled": True, "backend": "novaprime-http"})
            return
        if self.path == "/browser/status":
            self._send(200, {"ok": True, "transport": "browser", "capabilities": ["navigate", "click_selector"]})
            return
        if self.path == "/browser/pages":
            self._send(
                200,
                {
                    "status": "ok",
                    "count": 1,
                    "current_page_id": "page-1",
                    "pages": [
                        {"page_id": "page-1", "url": "https://example.com", "current": True}
                    ],
                },
            )
            return
        if self.path == "/terminal/sessions":
            self._send(
                200,
                [
                    {
                        "id": _Handler.terminal_session_id,
                        "open": True,
                        "command": ["/bin/bash", "-i"],
                        "last_seq": 3,
                    }
                ],
            )
            return
        if self.path == f"/terminal/sessions/{_Handler.terminal_session_id}":
            self._send(
                200,
                {
                    "id": _Handler.terminal_session_id,
                    "open": True,
                    "command": ["/bin/bash", "-i"],
                    "last_seq": 3,
                },
            )
            return
        if self.path == f"/terminal/sessions/{_Handler.terminal_session_id}/output?since_seq=0&limit=200":
            self._send(
                200,
                {
                    "id": _Handler.terminal_session_id,
                    "open": True,
                    "next_seq": 3,
                    "chunks": [
                        {"seq": 1, "data": "hello\n", "stream": "stdout"},
                        {"seq": 2, "data": "world\n", "stream": "stdout"},
                        {"seq": 3, "data": "$ ", "stream": "stdout"},
                    ],
                },
            )
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
            "/swarm/run",
            "/undo",
            "/check",
            "/auth/session",
            "/auth/session/revoke",
            "/auth/devices",
            "/auth/devices/remove",
            "/jobs/job-1/cancel",
            "/plans",
            "/plans/plan-1/approve",
            "/plans/plan-1/approve_async",
            "/plans/plan-1/retry_failed",
            "/plans/plan-1/retry_failed_async",
            "/plans/plan-1/reject",
            "/plans/plan-1/undo",
            "/plugins/novabridge/call",
            "/feedback",
            "/memory/recall",
            "/memory/ingest",
            "/browser/action",
            "/browser/navigate",
            "/browser/click",
            "/browser/fill",
            "/browser/extract_text",
            "/browser/screenshot",
            "/browser/wait_for_selector",
            "/browser/evaluate_js",
            "/browser/close",
            "/terminal/sessions",
            f"/terminal/sessions/{_Handler.terminal_session_id}/input",
            f"/terminal/sessions/{_Handler.terminal_session_id}/close",
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
            elif self.path == "/swarm/run":
                self._send(
                    202,
                    {
                        "status": "queued",
                        "kind": "swarm",
                        "submitted_jobs": len(payload.get("objectives") or []),
                        "jobs": [{"job_id": "job-1"}, {"job_id": "job-2"}],
                    },
                )
            elif self.path == "/jobs/job-1/cancel":
                self._send(200, {"id": "job-1", "status": "canceled", "canceled": True})
            elif self.path == "/plans":
                self._send(201, {"id": "plan-1", "status": "pending"})
            elif self.path == "/plans/plan-1/approve":
                self._send(200, {"id": "plan-1", "status": "executed"})
            elif self.path == "/plans/plan-1/approve_async":
                self._send(202, {"job_id": "job-plan-1", "status": "queued", "kind": "plan_approval"})
            elif self.path == "/plans/plan-1/retry_failed":
                self._send(200, {"id": "plan-1", "status": "executed"})
            elif self.path == "/plans/plan-1/retry_failed_async":
                self._send(202, {"job_id": "job-plan-1-retry", "status": "queued", "kind": "plan_retry_failed"})
            elif self.path == "/plans/plan-1/reject":
                self._send(200, {"id": "plan-1", "status": "rejected"})
            elif self.path == "/plans/plan-1/undo":
                self._send(200, {"plan_id": "plan-1", "results": [{"id": 1, "ok": True}]})
            elif self.path == "/plugins/novabridge/call":
                self._send(
                    200,
                    {
                        "plugin": "novabridge",
                        "route": payload.get("route"),
                        "method": payload.get("method"),
                        "ok": True,
                    },
                )
            elif self.path == "/feedback":
                self._send(200, {"ok": True, "id": "feedback-1", "rating": payload.get("rating")})
            elif self.path == "/memory/recall":
                self._send(
                    200,
                    {
                        "query": payload.get("query"),
                        "top_k": payload.get("top_k", 10),
                        "count": 1,
                        "memories": [{"content": "remembered", "score": 0.9}],
                    },
                )
            elif self.path == "/memory/ingest":
                self._send(
                    200,
                    {
                        "ok": True,
                        "source_id": payload.get("source_id", ""),
                        "result": {"ingested": True},
                    },
                )
            elif self.path == "/browser/action":
                action_payload = payload.get("action") if isinstance(payload.get("action"), dict) else payload
                self._send(
                    200,
                    {
                        "status": "ok",
                        "output": "browser action",
                        "action": action_payload,
                    },
                )
            elif self.path == "/browser/navigate":
                self._send(
                    200,
                    {
                        "status": "ok",
                        "output": "navigated",
                        "data": {"url": payload.get("url")},
                    },
                )
            elif self.path == "/browser/click":
                self._send(200, {"status": "ok", "output": "clicked", "data": {"selector": payload.get("selector")}})
            elif self.path == "/browser/fill":
                self._send(200, {"status": "ok", "output": "filled", "data": {"selector": payload.get("selector")}})
            elif self.path == "/browser/extract_text":
                self._send(
                    200,
                    {
                        "status": "ok",
                        "output": "extracted",
                        "data": {"text": "hello world", "selector": payload.get("selector", "body")},
                    },
                )
            elif self.path == "/browser/screenshot":
                self._send(200, {"status": "ok", "output": "saved", "data": {"path": "/tmp/shot.png"}})
            elif self.path == "/browser/wait_for_selector":
                self._send(200, {"status": "ok", "output": "ready", "data": {"selector": payload.get("selector")}})
            elif self.path == "/browser/evaluate_js":
                self._send(200, {"status": "ok", "output": "evaluated", "data": {"result": 42}})
            elif self.path == "/browser/close":
                self._send(200, {"status": "ok", "output": "browser session closed"})
            elif self.path == "/terminal/sessions":
                self._send(
                    201,
                    {
                        "id": _Handler.terminal_session_id,
                        "open": True,
                        "command": ["/bin/bash", "-i"],
                        "last_seq": 0,
                    },
                )
            elif self.path == f"/terminal/sessions/{_Handler.terminal_session_id}/input":
                self._send(200, {"id": _Handler.terminal_session_id, "accepted": True, "bytes": len(payload.get("input", ""))})
            elif self.path == f"/terminal/sessions/{_Handler.terminal_session_id}/close":
                self._send(200, {"id": _Handler.terminal_session_id, "closed": True})
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
            elif self.path == "/auth/devices":
                device_id = str(payload.get("device_id", "")).strip()
                if not device_id:
                    self._send(400, {"error": "'device_id' is required"})
                    return
                added = device_id not in _Handler.allowed_devices
                _Handler.allowed_devices.add(device_id)
                devices = sorted(_Handler.allowed_devices)
                self._send(
                    200,
                    {
                        "status": "ok",
                        "added": added,
                        "device_id": device_id,
                        "enabled": len(devices) > 0,
                        "count": len(devices),
                        "devices": devices,
                    },
                )
            elif self.path == "/auth/devices/remove":
                device_id = str(payload.get("device_id", "")).strip()
                if not device_id:
                    self._send(400, {"error": "'device_id' is required"})
                    return
                removed = device_id in _Handler.allowed_devices
                _Handler.allowed_devices.discard(device_id)
                devices = sorted(_Handler.allowed_devices)
                self._send(
                    200,
                    {
                        "status": "ok",
                        "removed": removed,
                        "device_id": device_id,
                        "enabled": len(devices) > 0,
                        "count": len(devices),
                        "devices": devices,
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
        _Handler.terminal_session_id = "term-1"
        _Handler.allowed_devices = set()
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
        self.assertEqual(client.plugins()[0]["name"], "novabridge")
        self.assertTrue(client.plugin_health("novabridge")["ok"])
        self.assertEqual(
            client.plugin_call("novabridge", route="/scene/list", method="GET")["plugin"],
            "novabridge",
        )
        self.assertEqual(client.run("demo", idempotency_key="idem-1")["idempotency"], "idem-1")
        self.assertEqual(client.run_async("demo")["status"], "queued")
        self.assertEqual(client.run_swarm(["demo-a", "demo-b"])["submitted_jobs"], 2)
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
        self.assertEqual(client.retry_failed_plan_async("plan-1")["kind"], "plan_retry_failed")
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
        self.assertEqual(client.allowed_devices()["count"], 0)
        add_device_payload = client.add_allowed_device("iphone-1")
        self.assertTrue(add_device_payload["added"])
        self.assertEqual(add_device_payload["count"], 1)
        remove_device_payload = client.remove_allowed_device("iphone-1")
        self.assertTrue(remove_device_payload["removed"])
        self.assertEqual(remove_device_payload["count"], 0)
        feedback_payload = client.submit_feedback(rating=8, objective="demo", notes="good flow")
        self.assertTrue(feedback_payload["ok"])
        self.assertEqual(feedback_payload["rating"], 8)
        self.assertTrue(client.memory_status()["ok"])
        self.assertTrue(client.novaprime_status()["ok"])
        recall_payload = client.memory_recall("excel formatting", top_k=3)
        self.assertEqual(recall_payload["query"], "excel formatting")
        self.assertEqual(recall_payload["count"], 1)
        ingest_payload = client.memory_ingest(
            "Remember this",
            source_id="test-1",
            metadata={"scope": "test"},
            idempotency_key="idem-memory-1",
        )
        self.assertTrue(ingest_payload["ok"])
        browser_status = client.browser_status()
        self.assertTrue(browser_status["ok"])
        self.assertEqual(browser_status["transport"], "browser")
        browser_pages = client.browser_pages()
        self.assertEqual(browser_pages["count"], 1)
        self.assertEqual(browser_pages["current_page_id"], "page-1")
        browser_action = client.browser_action({"type": "navigate", "target": "https://example.com"})
        self.assertEqual(browser_action["status"], "ok")
        self.assertEqual(browser_action["action"]["type"], "navigate")
        self.assertEqual(client.browser_navigate("https://example.com")["status"], "ok")
        self.assertEqual(client.browser_click("#ok")["status"], "ok")
        self.assertEqual(client.browser_fill("#search", "novaadapt")["status"], "ok")
        self.assertEqual(client.browser_extract_text("#title")["status"], "ok")
        self.assertEqual(client.browser_screenshot(path="shot.png")["status"], "ok")
        self.assertEqual(client.browser_wait_for_selector("#app")["status"], "ok")
        self.assertEqual(client.browser_evaluate_js("() => 42")["status"], "ok")
        self.assertEqual(client.browser_close()["status"], "ok")
        session = client.start_terminal_session(command="echo hi")
        session_id = session["id"]
        self.assertEqual(client.terminal_session(session_id)["id"], session_id)
        output = client.terminal_output(session_id, since_seq=0, limit=200)
        self.assertGreaterEqual(len(output["chunks"]), 1)
        self.assertTrue(client.terminal_input(session_id, "pwd\n")["accepted"])
        self.assertTrue(client.terminal_close(session_id)["closed"])
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

    def test_http_error_response_is_closed(self):
        class _ClosingHTTPError(error.HTTPError):
            def __init__(self):
                super().__init__(
                    url="http://127.0.0.1:1/models",
                    code=502,
                    msg="Bad Gateway",
                    hdrs=None,
                    fp=None,
                )
                self.closed = False

            def read(self):
                return b'{"error":"temporary upstream"}'

            def close(self):
                self.closed = True

        err = _ClosingHTTPError()

        def _raise(*_args, **_kwargs):
            raise err

        original = api_client_module.request.urlopen
        api_client_module.request.urlopen = _raise
        try:
            client = NovaAdaptAPIClient(
                base_url="http://127.0.0.1:1",
                token="token",
                max_retries=0,
            )
            with self.assertRaises(APIClientError):
                client.models()
        finally:
            api_client_module.request.urlopen = original

        self.assertTrue(err.closed)

    def test_url_error_reason_close_is_called(self):
        class _ClosableReason:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

            def __str__(self):
                return "transport down"

        reason = _ClosableReason()

        def _raise(*_args, **_kwargs):
            raise error.URLError(reason)

        original = api_client_module.request.urlopen
        api_client_module.request.urlopen = _raise
        try:
            client = NovaAdaptAPIClient(
                base_url="http://127.0.0.1:1",
                token="token",
                max_retries=0,
            )
            with self.assertRaises(APIClientError):
                client.models()
        finally:
            api_client_module.request.urlopen = original

        self.assertTrue(reason.closed)


if __name__ == "__main__":
    unittest.main()
