import json
import socketserver
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from novaadapt_core.directshell import DirectShellClient
from novaadapt_core.native_executor import NativeDesktopExecutor


class _Handler(BaseHTTPRequestHandler):
    required_token: str | None = None
    last_token: str | None = None

    def do_GET(self):
        token = self.headers.get("X-DirectShell-Token")
        _Handler.last_token = token
        if _Handler.required_token and token != _Handler.required_token:
            self.send_response(401)
            self.end_headers()
            return
        if self.path == "/health":
            body = json.dumps({"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        token = self.headers.get("X-DirectShell-Token")
        _Handler.last_token = token
        if _Handler.required_token and token != _Handler.required_token:
            self.send_response(401)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw)
        action = payload.get("action", {})
        body = json.dumps(
            {
                "status": "ok",
                "output": f"received:{action.get('type', 'unknown')}",
            }
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class _DaemonHandler(socketserver.StreamRequestHandler):
    required_token: str | None = None
    last_token: str | None = None

    def handle(self):
        raw_len = self.rfile.read(4)
        if len(raw_len) != 4:
            return
        size = int.from_bytes(raw_len, byteorder="big")
        raw = self.rfile.read(size).decode("utf-8")
        payload = json.loads(raw)
        token = payload.get("token") if isinstance(payload, dict) else None
        _DaemonHandler.last_token = str(token) if token is not None else None
        if _DaemonHandler.required_token and _DaemonHandler.last_token != _DaemonHandler.required_token:
            body = json.dumps({"status": "failed", "output": "unauthorized"}).encode("utf-8")
            self.wfile.write(len(body).to_bytes(4, byteorder="big") + body)
            return
        action = payload.get("action", {})
        body = json.dumps(
            {
                "status": "ok",
                "output": f"daemon:{action.get('type', 'unknown')}",
            }
        ).encode("utf-8")
        self.wfile.write(len(body).to_bytes(4, byteorder="big") + body)


class _DaemonServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class DirectShellClientTests(unittest.TestCase):
    def test_default_transport_is_native(self):
        client = DirectShellClient()
        self.assertEqual(client.transport, "native")

    def test_native_transport_wait_action_executes(self):
        client = DirectShellClient(transport="native")
        result = client.execute_action({"type": "wait", "value": "0.001s"}, dry_run=False)
        self.assertEqual(result.status, "ok")
        self.assertIn("waited", result.output)

    def test_http_transport_executes_action(self):
        _Handler.required_token = None
        _Handler.last_token = None
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(transport="http", http_url=f"http://127.0.0.1:{port}/execute")
            result = client.execute_action({"type": "click", "target": "OK"}, dry_run=False)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertIn("received:click", result.output)

    def test_http_transport_executes_action_with_token(self):
        _Handler.required_token = "secret-http"
        _Handler.last_token = None
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="http",
                http_url=f"http://127.0.0.1:{port}/execute",
                http_token="secret-http",
            )
            result = client.execute_action({"type": "click", "target": "OK"}, dry_run=False)
        finally:
            _Handler.required_token = None
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertEqual(_Handler.last_token, "secret-http")

    def test_rejects_unknown_transport(self):
        with self.assertRaises(RuntimeError):
            DirectShellClient(transport="invalid")

    def test_rejects_unknown_native_fallback_transport(self):
        with self.assertRaises(RuntimeError):
            DirectShellClient(transport="native", native_fallback_transport="invalid")

    def test_native_transport_falls_back_to_http(self):
        _Handler.required_token = None
        _Handler.last_token = None
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="native",
                native_fallback_transport="http",
                http_url=f"http://127.0.0.1:{port}/execute",
            )
            result = client.execute_action({"type": "click", "target": "OK"}, dry_run=False)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertIn("received:click", result.output)
        self.assertIn("native fallback after:", result.output)

    def test_daemon_transport_executes_action(self):
        _DaemonHandler.required_token = None
        _DaemonHandler.last_token = None
        server = _DaemonServer(("127.0.0.1", 0), _DaemonHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="daemon",
                daemon_socket="",
                daemon_host="127.0.0.1",
                daemon_port=port,
            )
            result = client.execute_action({"type": "type", "target": "hello"}, dry_run=False)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertIn("daemon:type", result.output)

    def test_daemon_transport_executes_action_with_token(self):
        _DaemonHandler.required_token = "secret-daemon"
        _DaemonHandler.last_token = None
        server = _DaemonServer(("127.0.0.1", 0), _DaemonHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="daemon",
                daemon_socket="",
                daemon_host="127.0.0.1",
                daemon_port=port,
                daemon_token="secret-daemon",
            )
            result = client.execute_action({"type": "type", "target": "hello"}, dry_run=False)
        finally:
            _DaemonHandler.required_token = None
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertEqual(_DaemonHandler.last_token, "secret-daemon")

    def test_probe_http_transport(self):
        _Handler.required_token = None
        _Handler.last_token = None
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(transport="http", http_url=f"http://127.0.0.1:{port}/execute")
            probe = client.probe()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertTrue(probe["ok"])
        self.assertEqual(probe["transport"], "http")

    def test_probe_http_transport_unauthorized_without_token(self):
        _Handler.required_token = "secret-http"
        _Handler.last_token = None
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(transport="http", http_url=f"http://127.0.0.1:{port}/execute")
            probe = client.probe()
        finally:
            _Handler.required_token = None
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertFalse(probe["ok"])
        self.assertEqual(probe["status_code"], 401)

    def test_probe_daemon_transport(self):
        _DaemonHandler.required_token = None
        _DaemonHandler.last_token = None
        server = _DaemonServer(("127.0.0.1", 0), _DaemonHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="daemon",
                daemon_socket="",
                daemon_host="127.0.0.1",
                daemon_port=port,
            )
            probe = client.probe()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertTrue(probe["ok"])
        self.assertEqual(probe["transport"], "daemon")

    def test_probe_subprocess_missing_binary(self):
        client = DirectShellClient(transport="subprocess", binary="missing-directshell-binary")
        probe = client.probe()
        self.assertFalse(probe["ok"])
        self.assertEqual(probe["transport"], "subprocess")

    def test_probe_native_includes_fallback_probe(self):
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="native",
                native_executor=NativeDesktopExecutor(platform_name="plan9"),
                native_fallback_transport="http",
                http_url=f"http://127.0.0.1:{port}/execute",
            )
            probe = client.probe()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertTrue(probe["ok"])
        self.assertEqual(probe["transport"], "native")
        self.assertEqual(probe["fallback_transport"], "http")
        self.assertIn("fallback_probe", probe)
        self.assertTrue(probe["fallback_probe"]["ok"])


if __name__ == "__main__":
    unittest.main()
