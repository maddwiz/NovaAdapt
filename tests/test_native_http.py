import json
import socket
import threading
import time
import unittest
from urllib import request

from novaadapt_core.directshell import DirectShellClient
from novaadapt_core.native_executor import NativeDesktopExecutor
from novaadapt_core.native_http import NativeExecutionHTTPServer


def _pick_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class NativeHTTPServerTests(unittest.TestCase):
    def test_http_server_executes_action(self):
        port = _pick_free_tcp_port()
        server = NativeExecutionHTTPServer(
            host="127.0.0.1",
            port=port,
            timeout_seconds=5,
            executor=NativeDesktopExecutor(platform_name="plan9"),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="http",
                http_url=f"http://127.0.0.1:{port}/execute",
                timeout_seconds=2,
            )
            deadline = time.time() + 2.0
            probe = {"ok": False}
            while time.time() < deadline:
                probe = client.probe()
                if bool(probe.get("ok")):
                    break
                time.sleep(0.05)
            self.assertTrue(bool(probe.get("ok")))

            result = client.execute_action({"type": "note", "value": "hello"}, dry_run=False)
        finally:
            server.shutdown()
            thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertIn("note:note hello", result.output)

    def test_http_server_token_enforcement(self):
        port = _pick_free_tcp_port()
        server = NativeExecutionHTTPServer(
            host="127.0.0.1",
            port=port,
            http_token="secret-http",
            timeout_seconds=5,
            executor=NativeDesktopExecutor(platform_name="plan9"),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            unauth_client = DirectShellClient(
                transport="http",
                http_url=f"http://127.0.0.1:{port}/execute",
                timeout_seconds=2,
            )
            auth_client = DirectShellClient(
                transport="http",
                http_url=f"http://127.0.0.1:{port}/execute",
                http_token="secret-http",
                timeout_seconds=2,
            )
            deadline = time.time() + 2.0
            probe = {"ok": False}
            while time.time() < deadline:
                probe = auth_client.probe()
                if bool(probe.get("ok")):
                    break
                time.sleep(0.05)
            self.assertTrue(bool(probe.get("ok")))

            unauth_probe = unauth_client.probe()
            unauth_result = unauth_client.execute_action({"type": "note", "value": "hello"}, dry_run=False)
            auth_result = auth_client.execute_action({"type": "note", "value": "hello"}, dry_run=False)
        finally:
            server.shutdown()
            thread.join(timeout=2)

        self.assertFalse(bool(unauth_probe.get("ok")))
        self.assertEqual(int(unauth_probe.get("status_code", 0)), 401)
        self.assertEqual(unauth_result.status, "failed")
        self.assertIn("HTTP 401", unauth_result.output)
        self.assertEqual(auth_result.status, "ok")
        self.assertIn("note:note hello", auth_result.output)

    def test_http_server_health_deep(self):
        port = _pick_free_tcp_port()
        server = NativeExecutionHTTPServer(
            host="127.0.0.1",
            port=port,
            timeout_seconds=5,
            executor=NativeDesktopExecutor(platform_name="plan9"),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            with request.urlopen(f"http://127.0.0.1:{port}/health?deep=1", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            thread.join(timeout=2)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["transport"], "http")
        self.assertIn("capabilities", payload)


if __name__ == "__main__":
    unittest.main()
