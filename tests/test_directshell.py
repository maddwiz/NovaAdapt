import json
import socketserver
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from novaadapt_core.directshell import DirectShellClient


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
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
    def handle(self):
        raw_len = self.rfile.read(4)
        if len(raw_len) != 4:
            return
        size = int.from_bytes(raw_len, byteorder="big")
        raw = self.rfile.read(size).decode("utf-8")
        payload = json.loads(raw)
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
    def test_http_transport_executes_action(self):
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

    def test_rejects_unknown_transport(self):
        client = DirectShellClient(transport="invalid")
        with self.assertRaises(RuntimeError):
            client.execute_action({"type": "click", "target": "OK"}, dry_run=False)

    def test_daemon_transport_executes_action(self):
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


if __name__ == "__main__":
    unittest.main()
