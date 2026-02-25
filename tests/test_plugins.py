import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from novaadapt_core.plugins.registry import PluginConfig, PluginRegistry


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/nova/health", "/bridge/health"}:
            self._send(200, {"ok": True})
            return
        if self.path == "/nova/caps":
            self._send(200, {"caps": ["scene"]})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/bridge/command":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw) if raw else {}
            self._send(200, {"status": "queued", "route": payload.get("route")})
            return
        self._send(404, {"error": "not found"})

    def _send(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *args):
        _ = args
        return


class PluginRegistryTests(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.host, self.port = self.server.server_address
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.registry = PluginRegistry(
            plugins={
                "novabridge": PluginConfig(
                    name="novabridge",
                    base_url=f"http://{self.host}:{self.port}/nova",
                    headers={},
                    health_paths=("/health", "/caps"),
                ),
                "novablox": PluginConfig(
                    name="novablox",
                    base_url=f"http://{self.host}:{self.port}/bridge",
                    headers={},
                    health_paths=("/health",),
                ),
            },
            timeout_seconds=3,
            max_response_bytes=1024 * 16,
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_list_and_health(self):
        plugins = self.registry.list_plugins()
        names = {item["name"] for item in plugins}
        self.assertIn("novabridge", names)
        self.assertIn("novablox", names)
        health = self.registry.health("novabridge")
        self.assertTrue(health["ok"])
        self.assertEqual(health["status_code"], 200)

    def test_call(self):
        result = self.registry.call(
            "novablox",
            route="/command",
            payload={"route": "/scene/spawn-object"},
            method="POST",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["response"]["status"], "queued")

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.registry.call("novabridge", route="missing-leading-slash")
        with self.assertRaises(ValueError):
            self.registry.call("unknown", route="/health")


if __name__ == "__main__":
    unittest.main()
