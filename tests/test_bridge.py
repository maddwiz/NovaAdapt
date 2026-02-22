import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request

from novaadapt_bridge.relay import create_server as create_bridge_server


class _CoreHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if auth != "Bearer coresecret":
            self._send(401, {"error": "unauthorized core"})
            return

        if self.path == "/models":
            self._send(200, [{"name": "local"}])
            return

        if self.path.startswith("/jobs/"):
            self._send(200, {"id": self.path.split("/")[-1], "status": "succeeded"})
            return

        self._send(404, {"error": "not found"})

    def do_POST(self):
        auth = self.headers.get("Authorization", "")
        if auth != "Bearer coresecret":
            self._send(401, {"error": "unauthorized core"})
            return

        if self.path == "/run_async":
            self._send(202, {"job_id": "abc123", "status": "queued"})
            return

        self._send(404, {"error": "not found"})

    def _send(self, status: int, payload: object):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class BridgeRelayTests(unittest.TestCase):
    def test_bridge_forwards_with_auth(self):
        core_server = ThreadingHTTPServer(("127.0.0.1", 0), _CoreHandler)
        core_host, core_port = core_server.server_address
        core_thread = threading.Thread(target=core_server.serve_forever, daemon=True)
        core_thread.start()

        bridge_server = create_bridge_server(
            host="127.0.0.1",
            port=0,
            core_base_url=f"http://{core_host}:{core_port}",
            bridge_token="bridgetoken",
            core_token="coresecret",
            timeout_seconds=5,
        )
        bridge_host, bridge_port = bridge_server.server_address
        bridge_thread = threading.Thread(target=bridge_server.serve_forever, daemon=True)
        bridge_thread.start()

        try:
            with self.assertRaises(error.HTTPError) as err:
                _get_json(f"http://{bridge_host}:{bridge_port}/models")
            self.assertEqual(err.exception.code, 401)

            models = _get_json(
                f"http://{bridge_host}:{bridge_port}/models",
                token="bridgetoken",
            )
            self.assertEqual(models[0]["name"], "local")

            queued = _post_json(
                f"http://{bridge_host}:{bridge_port}/run_async",
                {"objective": "test"},
                token="bridgetoken",
            )
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(queued["job_id"], "abc123")

            job = _get_json(
                f"http://{bridge_host}:{bridge_port}/jobs/abc123",
                token="bridgetoken",
            )
            self.assertEqual(job["status"], "succeeded")
        finally:
            bridge_server.shutdown()
            bridge_server.server_close()
            bridge_thread.join(timeout=2)

            core_server.shutdown()
            core_server.server_close()
            core_thread.join(timeout=2)


def _get_json(url: str, token: str | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict, token: str | None = None):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url=url, data=data, headers=headers, method="POST")
    with request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
