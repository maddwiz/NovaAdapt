import io
import json
import logging
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from novaadapt_core.directshell import ExecutionResult
from novaadapt_core.server import (
    _PerClientSlidingWindowRateLimiter,
    _parse_trusted_proxy_cidrs,
    create_server,
)
from novaadapt_core.service import NovaAdaptService
from novaadapt_shared.model_router import RouterResult


class _StubRouter:
    def list_models(self):
        class Model:
            def __init__(self, name, model, provider, base_url):
                self.name = name
                self.model = model
                self.provider = provider
                self.base_url = base_url

        return [Model("local", "qwen", "openai-compatible", "http://localhost:11434/v1")]

    def health_check(self, model_names=None, probe_prompt="Reply with: OK"):
        return [{"name": "local", "ok": True, "latency_ms": 1.0}]

    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
        return RouterResult(
            model_name=model_name or "local",
            model_id="qwen",
            content='{"actions":[{"type":"click","target":"OK"}]}',
            strategy=strategy,
            votes={},
            errors={},
            attempted_models=[model_name or "local"],
        )


class _StubDirectShell:
    def execute_action(self, action, dry_run=True):
        return ExecutionResult(action=action, status="preview" if dry_run else "ok", output="simulated")


class _FlakyDirectShell:
    attempts = 0

    def execute_action(self, action, dry_run=True):
        if dry_run:
            return ExecutionResult(action=action, status="preview", output="simulated")
        _FlakyDirectShell.attempts += 1
        if _FlakyDirectShell.attempts == 1:
            return ExecutionResult(action=action, status="failed", output="transient failure")
        return ExecutionResult(action=action, status="ok", output="recovered")


class ServerTests(unittest.TestCase):
    def test_http_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                health, health_headers = _get_json_with_headers(f"http://{host}:{port}/health")
                self.assertTrue(health["ok"])
                self.assertIn("request_id", health)
                self.assertTrue(health_headers.get("X-Request-ID"))

                deep_health, _ = _get_json_with_headers(f"http://{host}:{port}/health?deep=1")
                self.assertTrue(deep_health["ok"])
                self.assertIn("checks", deep_health)
                self.assertTrue(deep_health["checks"]["models"]["ok"])
                self.assertTrue(deep_health["checks"]["audit_store"]["ok"])
                self.assertIn("metrics", deep_health)

                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/health?deep=1&execution=1")
                self.assertEqual(err.exception.code, 503)
                execution_health = json.loads(err.exception.read().decode("utf-8"))
                self.assertFalse(execution_health["ok"])
                self.assertIn("directshell", execution_health["checks"])
                self.assertFalse(execution_health["checks"]["directshell"]["ok"])

                dashboard_html = _get_text(f"http://{host}:{port}/dashboard")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_html)
                self.assertIn("Approve Async", dashboard_html)
                self.assertIn("cancel-job", dashboard_html)

                dashboard_data, _ = _get_json_with_headers(f"http://{host}:{port}/dashboard/data")
                self.assertTrue(dashboard_data["health"]["ok"])
                self.assertIn("metrics", dashboard_data)
                self.assertIn("jobs", dashboard_data)
                self.assertIn("plans", dashboard_data)
                self.assertIn("events", dashboard_data)

                openapi, _ = _get_json_with_headers(f"http://{host}:{port}/openapi.json")
                self.assertEqual(openapi["openapi"], "3.1.0")
                self.assertIn("/run", openapi["paths"])
                self.assertIn("/jobs/{id}/cancel", openapi["paths"])
                self.assertIn("/jobs/{id}/stream", openapi["paths"])
                self.assertIn("/plans/{id}/stream", openapi["paths"])
                self.assertIn("/plans/{id}/approve", openapi["paths"])
                self.assertIn("/plans/{id}/approve_async", openapi["paths"])
                self.assertIn("/plans/{id}/retry_failed", openapi["paths"])
                self.assertIn("/plans/{id}/retry_failed_async", openapi["paths"])
                self.assertIn("/plans/{id}/undo", openapi["paths"])
                self.assertIn("/dashboard/data", openapi["paths"])
                self.assertIn("/events", openapi["paths"])
                self.assertIn("/events/stream", openapi["paths"])

                models, _ = _get_json_with_headers(f"http://{host}:{port}/models")
                self.assertEqual(models[0]["name"], "local")

                run, _ = _post_json_with_headers(
                    f"http://{host}:{port}/run",
                    {"objective": "click ok"},
                )
                self.assertEqual(run["results"][0]["status"], "preview")
                self.assertIn("request_id", run)

                events, _ = _get_json_with_headers(f"http://{host}:{port}/events?limit=10")
                self.assertGreaterEqual(len(events), 1)
                self.assertEqual(events[0]["category"], "run")

                history, _ = _get_json_with_headers(f"http://{host}:{port}/history?limit=5")
                self.assertEqual(len(history), 1)

                created_plan, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok"},
                )
                self.assertEqual(created_plan["status"], "pending")
                plan_id = created_plan["id"]

                plan_list, _ = _get_json_with_headers(f"http://{host}:{port}/plans?limit=5")
                self.assertGreaterEqual(len(plan_list), 1)

                plan_item, _ = _get_json_with_headers(f"http://{host}:{port}/plans/{plan_id}")
                self.assertEqual(plan_item["id"], plan_id)

                approved_plan, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plans/{plan_id}/approve",
                    {"execute": True},
                )
                self.assertEqual(approved_plan["status"], "executed")
                self.assertEqual(len(approved_plan.get("execution_results") or []), 1)

                with self.assertRaises(error.HTTPError) as err:
                    _post_json(
                        f"http://{host}:{port}/plans/{plan_id}/retry_failed",
                        {"allow_dangerous": True},
                    )
                self.assertEqual(err.exception.code, 400)

                plan_stream = _get_text(
                    f"http://{host}:{port}/plans/{plan_id}/stream?timeout=2&interval=0.05"
                )
                self.assertIn("event: plan", plan_stream)
                self.assertIn("event: end", plan_stream)

                events_stream = _get_text(f"http://{host}:{port}/events/stream?timeout=1&interval=0.05&since_id=0")
                self.assertIn("event: audit", events_stream)

                undo_plan, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plans/{plan_id}/undo",
                    {"mark_only": True},
                )
                self.assertEqual(undo_plan["plan_id"], plan_id)
                self.assertTrue(all(item.get("ok") for item in undo_plan["results"]))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_token_auth_and_async_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            jobs_db = Path(tmp) / "jobs.db"
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(jobs_db),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/models")
                self.assertEqual(err.exception.code, 401)

                models = _get_json(f"http://{host}:{port}/models", token="secret")
                self.assertEqual(models[0]["name"], "local")

                dashboard_html = _get_text(f"http://{host}:{port}/dashboard", token="secret")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_html)
                self.assertIn("Approve Async", dashboard_html)

                dashboard_with_query = _get_text(f"http://{host}:{port}/dashboard?token=secret")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_with_query)

                dashboard_data = _get_json(f"http://{host}:{port}/dashboard/data?token=secret")
                self.assertTrue(dashboard_data["health"]["ok"])
                self.assertIn("metrics", dashboard_data)
                self.assertIn("events", dashboard_data)

                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/events")
                self.assertEqual(err.exception.code, 401)

                queued = _post_json(
                    f"http://{host}:{port}/run_async",
                    {"objective": "click ok"},
                    token="secret",
                )
                self.assertEqual(queued["status"], "queued")
                job_id = queued["job_id"]

                stream = _get_text(
                    f"http://{host}:{port}/jobs/{job_id}/stream?timeout=2&interval=0.05",
                    token="secret",
                )
                self.assertIn("event: job", stream)
                self.assertIn(job_id, stream)

                cancel = _post_json(
                    f"http://{host}:{port}/jobs/{job_id}/cancel",
                    {},
                    token="secret",
                )
                self.assertEqual(cancel["id"], job_id)

                # Poll briefly for completion.
                terminal = None
                for _ in range(30):
                    terminal = _get_json(f"http://{host}:{port}/jobs/{job_id}", token="secret")
                    if terminal["status"] in {"succeeded", "failed"}:
                        break
                    time.sleep(0.02)

                self.assertIsNotNone(terminal)
                self.assertIn(terminal["status"], {"succeeded", "running", "queued", "canceled"})

                created_plan = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok"},
                    token="secret",
                )
                self.assertEqual(created_plan["status"], "pending")

                queued_plan = _post_json(
                    f"http://{host}:{port}/plans/{created_plan['id']}/approve_async",
                    {"execute": True},
                    token="secret",
                )
                self.assertEqual(queued_plan["status"], "queued")
                self.assertEqual(queued_plan["kind"], "plan_approval")
                approval_job_id = queued_plan["job_id"]

                terminal_plan_job = None
                for _ in range(30):
                    terminal_plan_job = _get_json(f"http://{host}:{port}/jobs/{approval_job_id}", token="secret")
                    if terminal_plan_job["status"] in {"succeeded", "failed", "canceled"}:
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(terminal_plan_job)
                self.assertIn(terminal_plan_job["status"], {"succeeded", "running", "queued", "canceled"})

                created_plan_2 = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok again"},
                    token="secret",
                )
                rejected_plan = _post_json(
                    f"http://{host}:{port}/plans/{created_plan_2['id']}/reject",
                    {"reason": "manual deny"},
                    token="secret",
                )
                self.assertEqual(rejected_plan["status"], "rejected")

                events = _get_json(f"http://{host}:{port}/events?limit=20", token="secret")
                self.assertGreaterEqual(len(events), 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            # Verify job history is retained across server restart.
            server2 = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(jobs_db),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host2, port2 = server2.server_address
            thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
            thread2.start()
            try:
                jobs_list = _get_json(f"http://{host2}:{port2}/jobs?limit=10", token="secret")
                self.assertGreaterEqual(len(jobs_list), 1)
            finally:
                server2.shutdown()
                server2.server_close()
                thread2.join(timeout=2)

    def test_retry_failed_async_route_queues_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            _FlakyDirectShell.attempts = 0
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_FlakyDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(Path(tmp) / "jobs.db"),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                created_plan = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok"},
                    token="secret",
                )
                plan_id = created_plan["id"]

                failed_plan = _post_json(
                    f"http://{host}:{port}/plans/{plan_id}/approve",
                    {"execute": True},
                    token="secret",
                )
                self.assertEqual(failed_plan["status"], "failed")

                queued_retry = _post_json(
                    f"http://{host}:{port}/plans/{plan_id}/retry_failed_async",
                    {"allow_dangerous": True, "action_retry_attempts": 2, "action_retry_backoff_seconds": 0.0},
                    token="secret",
                )
                self.assertEqual(queued_retry["status"], "queued")
                self.assertEqual(queued_retry["kind"], "plan_retry_failed")
                retry_job_id = queued_retry["job_id"]

                terminal_retry_job = None
                for _ in range(40):
                    terminal_retry_job = _get_json(f"http://{host}:{port}/jobs/{retry_job_id}", token="secret")
                    if terminal_retry_job["status"] in {"succeeded", "failed", "canceled"}:
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(terminal_retry_job)
                self.assertEqual(terminal_retry_job["status"], "succeeded")

                retried_plan = _get_json(f"http://{host}:{port}/plans/{plan_id}", token="secret")
                self.assertEqual(retried_plan["status"], "executed")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_request_id_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                body, headers = _get_json_with_headers(
                    f"http://{host}:{port}/models",
                    token="secret",
                    request_id="rid-123",
                )
                self.assertEqual(body[0]["name"], "local")
                self.assertEqual(headers.get("X-Request-ID"), "rid-123")

                run, headers = _post_json_with_headers(
                    f"http://{host}:{port}/run",
                    {"objective": "click ok"},
                    token="secret",
                    request_id="rid-xyz",
                )
                self.assertEqual(run["request_id"], "rid-xyz")
                self.assertEqual(headers.get("X-Request-ID"), "rid-xyz")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_request_logs_redact_query_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            stream = io.StringIO()
            logger = logging.getLogger("novaadapt.tests.server.log_redaction")
            logger.setLevel(logging.INFO)
            logger.handlers = []
            logger.propagate = False
            handler = logging.StreamHandler(stream)
            logger.addHandler(handler)

            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                log_requests=True,
                logger=logger,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                html = _get_text(f"http://{host}:{port}/dashboard?token=secret")
                self.assertIn("NovaAdapt Core Dashboard", html)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                logger.removeHandler(handler)
                handler.close()

            output = stream.getvalue()
            self.assertIn("/dashboard?token=redacted", output)
            self.assertNotIn("token=secret", output)

    def test_metrics_endpoint_and_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                with self.assertRaises(error.HTTPError) as err:
                    _get_text(f"http://{host}:{port}/metrics")
                self.assertEqual(err.exception.code, 401)

                _ = _get_json(f"http://{host}:{port}/models", token="secret")
                metrics = _get_text(f"http://{host}:{port}/metrics", token="secret")
                self.assertIn("novaadapt_core_requests_total", metrics)
                self.assertIn("novaadapt_core_unauthorized_total", metrics)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_rate_limit_and_max_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                rate_limit_rps=1,
                rate_limit_burst=1,
                max_request_body_bytes=128,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _ = _get_json(f"http://{host}:{port}/models", token="secret")
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/models", token="secret")
                self.assertEqual(err.exception.code, 429)

                time.sleep(1.05)
                with self.assertRaises(error.HTTPError) as err:
                    _post_json(
                        f"http://{host}:{port}/run",
                        {"objective": "x" * 1024},
                        token="secret",
                    )
                self.assertEqual(err.exception.code, 413)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_per_client_rate_limiter_keys_are_isolated(self):
        limiter = _PerClientSlidingWindowRateLimiter(burst=1, window_seconds=1.0, idle_ttl_seconds=60.0)
        self.assertTrue(limiter.allow("client-a"))
        self.assertFalse(limiter.allow("client-a"))
        self.assertTrue(limiter.allow("client-b"))

    def test_parse_trusted_proxy_cidrs(self):
        networks = _parse_trusted_proxy_cidrs(["127.0.0.1/32", "10.0.0.1"])
        self.assertEqual(len(networks), 2)
        with self.assertRaises(ValueError):
            _parse_trusted_proxy_cidrs(["invalid-cidr"])

    def test_rate_limit_ignores_forwarded_for_without_trusted_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                rate_limit_rps=1,
                rate_limit_burst=1,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _ = _get_json(
                    f"http://{host}:{port}/models",
                    token="secret",
                    extra_headers={"X-Forwarded-For": "198.51.100.20"},
                )
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(
                        f"http://{host}:{port}/models",
                        token="secret",
                        extra_headers={"X-Forwarded-For": "198.51.100.21"},
                    )
                self.assertEqual(err.exception.code, 429)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_rate_limit_uses_forwarded_for_with_trusted_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                rate_limit_rps=1,
                rate_limit_burst=1,
                trusted_proxy_cidrs=["127.0.0.1/32"],
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _ = _get_json(
                    f"http://{host}:{port}/models",
                    token="secret",
                    extra_headers={"X-Forwarded-For": "198.51.100.20"},
                )
                _ = _get_json(
                    f"http://{host}:{port}/models",
                    token="secret",
                    extra_headers={"X-Forwarded-For": "198.51.100.21"},
                )
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(
                        f"http://{host}:{port}/models",
                        token="secret",
                        extra_headers={"X-Forwarded-For": "198.51.100.21"},
                    )
                self.assertEqual(err.exception.code, 429)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_idempotency_replay_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(Path(tmp) / "jobs.db"),
                idempotency_db_path=str(Path(tmp) / "idempotency.db"),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                first, _ = _post_json_with_headers(
                    f"http://{host}:{port}/run_async",
                    {"objective": "click ok"},
                    token="secret",
                    idempotency_key="idem-1",
                )
                second, headers = _post_json_with_headers(
                    f"http://{host}:{port}/run_async",
                    {"objective": "click ok"},
                    token="secret",
                    idempotency_key="idem-1",
                )
                self.assertEqual(first["job_id"], second["job_id"])
                self.assertEqual(headers.get("X-Idempotency-Replayed"), "true")
                self.assertEqual(headers.get("Idempotency-Key"), "idem-1")

                with self.assertRaises(error.HTTPError) as err:
                    _post_json(
                        f"http://{host}:{port}/run_async",
                        {"objective": "different"},
                        token="secret",
                        idempotency_key="idem-1",
                    )
                self.assertEqual(err.exception.code, 409)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_audit_retention_prunes_expired_events_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_db = Path(tmp) / "events.db"
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                audit_db_path=str(events_db),
                audit_retention_seconds=1,
                audit_cleanup_interval_seconds=0,
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _post_json(f"http://{host}:{port}/run", {"objective": "first run"})
                first_events = _get_json(f"http://{host}:{port}/events?limit=10")
                self.assertGreaterEqual(len(first_events), 1)
                stale_event_id = int(first_events[0]["id"])

                old_timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
                with closing(sqlite3.connect(events_db)) as conn:
                    conn.execute(
                        "UPDATE audit_events SET created_at = ? WHERE id = ?",
                        (old_timestamp, stale_event_id),
                    )
                    conn.commit()

                _post_json(f"http://{host}:{port}/run", {"objective": "second run"})
                second_events = _get_json(f"http://{host}:{port}/events?limit=10")
                ids = {int(item["id"]) for item in second_events}
                self.assertNotIn(stale_event_id, ids)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


def _get_json(url: str, token: str | None = None, extra_headers: dict[str, str] | None = None):
    return _get_json_with_headers(url=url, token=token, extra_headers=extra_headers)[0]


def _post_json(
    url: str,
    payload: dict,
    token: str | None = None,
    idempotency_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    return _post_json_with_headers(
        url=url,
        payload=payload,
        token=token,
        idempotency_key=idempotency_key,
        extra_headers=extra_headers,
    )[0]


def _get_text(url: str, token: str | None = None, extra_headers: dict[str, str] | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=5) as response:
        return response.read().decode("utf-8")


def _get_json_with_headers(
    url: str,
    token: str | None = None,
    request_id: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["X-Request-ID"] = request_id
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
        return body, dict(response.headers)


def _post_json_with_headers(
    url: str,
    payload: dict,
    token: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["X-Request-ID"] = request_id
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(
        url=url,
        data=data,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
        return body, dict(response.headers)


if __name__ == "__main__":
    unittest.main()
