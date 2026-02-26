import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
from urllib import error

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

    def test_http_error_response_is_closed(self):
        class _ClosingHTTPError(error.HTTPError):
            def __init__(self):
                super().__init__(
                    url="http://plugin.local/missing",
                    code=404,
                    msg="Not Found",
                    hdrs=None,
                    fp=None,
                )
                self._body = b'{"error":"missing"}'
                self.closed = False

            def read(self, amt=None):
                if amt is None or int(amt) < 0:
                    return self._body
                return self._body[: int(amt)]

            def close(self):
                self.closed = True

        err = _ClosingHTTPError()
        with mock.patch("novaadapt_core.plugins.registry.request.urlopen", side_effect=err):
            result = self.registry.call("novabridge", route="/missing", method="GET")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 404)
        self.assertTrue(err.closed)

    def test_url_error_reason_close_is_called(self):
        class _Reason:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

            def __str__(self):
                return "connection refused"

        reason = _Reason()
        with mock.patch(
            "novaadapt_core.plugins.registry.request.urlopen",
            side_effect=error.URLError(reason),
        ):
            result = self.registry.call("novabridge", route="/health", method="GET")

        self.assertFalse(result["ok"])
        self.assertEqual(result["status_code"], 0)
        self.assertTrue(reason.closed)


if __name__ == "__main__":
    unittest.main()
