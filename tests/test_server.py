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
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_token_auth_and_async_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server("127.0.0.1", 0, service, api_token="secret")
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/models")
                self.assertEqual(err.exception.code, 401)

                models = _get_json(f"http://{host}:{port}/models", token="secret")
                self.assertEqual(models[0]["name"], "local")

                queued = _post_json(
                    f"http://{host}:{port}/run_async",
                    {"objective": "click ok"},
                    token="secret",
                )
                self.assertEqual(queued["status"], "queued")
                job_id = queued["job_id"]

                # Poll briefly for completion.
                terminal = None
                for _ in range(30):
                    terminal = _get_json(f"http://{host}:{port}/jobs/{job_id}", token="secret")
                    if terminal["status"] in {"succeeded", "failed"}:
                        break
                    time.sleep(0.02)

                self.assertIsNotNone(terminal)
                self.assertEqual(terminal["status"], "succeeded")
                self.assertIsNotNone(terminal["result"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_request_id_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
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


def _get_json(url: str, token: str | None = None):
    return _get_json_with_headers(url=url, token=token)[0]


def _post_json(url: str, payload: dict, token: str | None = None):
    return _post_json_with_headers(url=url, payload=payload, token=token)[0]


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
