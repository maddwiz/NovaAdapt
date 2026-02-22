import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib import request

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
                health = _get_json(f"http://{host}:{port}/health")
                self.assertTrue(health["ok"])

                models = _get_json(f"http://{host}:{port}/models")
                self.assertEqual(models[0]["name"], "local")

                run = _post_json(
                    f"http://{host}:{port}/run",
                    {"objective": "click ok"},
                )
                self.assertEqual(run["results"][0]["status"], "preview")

                history = _get_json(f"http://{host}:{port}/history?limit=5")
                self.assertEqual(len(history), 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


def _get_json(url: str):
    with request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
