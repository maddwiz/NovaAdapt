import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib import error, request

from novaadapt_core.directshell import ExecutionResult
from novaadapt_core.server import create_server
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
            server = create_server("127.0.0.1", 0, service)
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                health, health_headers = _get_json_with_headers(f"http://{host}:{port}/health")
                self.assertTrue(health["ok"])
                self.assertIn("request_id", health)
                self.assertTrue(health_headers.get("X-Request-ID"))

                dashboard_html = _get_text(f"http://{host}:{port}/dashboard")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_html)

                dashboard_data, _ = _get_json_with_headers(f"http://{host}:{port}/dashboard/data")
                self.assertTrue(dashboard_data["health"]["ok"])
                self.assertIn("metrics", dashboard_data)
                self.assertIn("jobs", dashboard_data)
                self.assertIn("plans", dashboard_data)

                openapi, _ = _get_json_with_headers(f"http://{host}:{port}/openapi.json")
                self.assertEqual(openapi["openapi"], "3.1.0")
                self.assertIn("/run", openapi["paths"])
                self.assertIn("/jobs/{id}/cancel", openapi["paths"])
                self.assertIn("/jobs/{id}/stream", openapi["paths"])
                self.assertIn("/plans/{id}/approve", openapi["paths"])
                self.assertIn("/dashboard/data", openapi["paths"])

                models, _ = _get_json_with_headers(f"http://{host}:{port}/models")
                self.assertEqual(models[0]["name"], "local")

                run, _ = _post_json_with_headers(
                    f"http://{host}:{port}/run",
                    {"objective": "click ok"},
                )
                self.assertEqual(run["results"][0]["status"], "preview")
                self.assertIn("request_id", run)

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
            server = create_server("127.0.0.1", 0, service, api_token="secret", jobs_db_path=str(jobs_db))
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

                dashboard_with_query = _get_text(f"http://{host}:{port}/dashboard?token=secret")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_with_query)

                dashboard_data = _get_json(f"http://{host}:{port}/dashboard/data?token=secret")
                self.assertTrue(dashboard_data["health"]["ok"])
                self.assertIn("metrics", dashboard_data)

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

                rejected_plan = _post_json(
                    f"http://{host}:{port}/plans/{created_plan['id']}/reject",
                    {"reason": "manual deny"},
                    token="secret",
                )
                self.assertEqual(rejected_plan["status"], "rejected")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            # Verify job history is retained across server restart.
            server2 = create_server("127.0.0.1", 0, service, api_token="secret", jobs_db_path=str(jobs_db))
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

    def test_request_id_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server("127.0.0.1", 0, service, api_token="secret")
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

    def test_metrics_endpoint_and_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server("127.0.0.1", 0, service, api_token="secret")
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


def _get_json(url: str, token: str | None = None):
    return _get_json_with_headers(url=url, token=token)[0]


def _post_json(url: str, payload: dict, token: str | None = None):
    return _post_json_with_headers(url=url, payload=payload, token=token)[0]


def _get_text(url: str, token: str | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=5) as response:
        return response.read().decode("utf-8")


def _get_json_with_headers(url: str, token: str | None = None, request_id: str | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["X-Request-ID"] = request_id
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))
        return body, dict(response.headers)


def _post_json_with_headers(
    url: str,
    payload: dict,
    token: str | None = None,
    request_id: str | None = None,
):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["X-Request-ID"] = request_id
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
