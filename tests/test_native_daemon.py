import os
import socket
import tempfile
import threading
import time
import unittest

from novaadapt_core.directshell import DirectShellClient
from novaadapt_core.native_daemon import NativeExecutionDaemon
from novaadapt_core.native_executor import NativeDesktopExecutor


def _pick_free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class NativeDaemonTests(unittest.TestCase):
    def test_unix_socket_daemon_executes_action(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("unix sockets not supported on this platform")

        with tempfile.TemporaryDirectory() as tmp:
            socket_path = f"{tmp}/native-directshell.sock"
            daemon = NativeExecutionDaemon(
                socket_path=socket_path,
                timeout_seconds=5,
                executor=NativeDesktopExecutor(platform_name="plan9"),
            )
            thread = threading.Thread(target=daemon.serve_forever, daemon=True)
            thread.start()

            try:
                deadline = time.time() + 2.0
                while time.time() < deadline and not os.path.exists(socket_path):
                    time.sleep(0.01)
                self.assertTrue(os.path.exists(socket_path))
                client = DirectShellClient(
                    transport="daemon",
                    daemon_socket=socket_path,
                    timeout_seconds=2,
                )
                result = client.execute_action({"type": "note", "value": "hello"}, dry_run=False)
            finally:
                daemon.shutdown()
                thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertIn("note:note hello", result.output)

    def test_tcp_daemon_executes_action(self):
        port = _pick_free_tcp_port()
        daemon = NativeExecutionDaemon(
            socket_path="",
            host="127.0.0.1",
            port=port,
            timeout_seconds=5,
            executor=NativeDesktopExecutor(platform_name="plan9"),
        )
        thread = threading.Thread(target=daemon.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="daemon",
                daemon_socket="",
                daemon_host="127.0.0.1",
                daemon_port=port,
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
            daemon.shutdown()
            thread.join(timeout=2)

        self.assertEqual(result.status, "ok")
        self.assertIn("note:note hello", result.output)

    def test_tcp_daemon_token_enforcement(self):
        port = _pick_free_tcp_port()
        daemon = NativeExecutionDaemon(
            socket_path="",
            host="127.0.0.1",
            port=port,
            daemon_token="secret-daemon",
            timeout_seconds=5,
            executor=NativeDesktopExecutor(platform_name="plan9"),
        )
        thread = threading.Thread(target=daemon.serve_forever, daemon=True)
        thread.start()

        try:
            unauth_client = DirectShellClient(
                transport="daemon",
                daemon_socket="",
                daemon_host="127.0.0.1",
                daemon_port=port,
                timeout_seconds=2,
            )
            auth_client = DirectShellClient(
                transport="daemon",
                daemon_socket="",
                daemon_host="127.0.0.1",
                daemon_port=port,
                daemon_token="secret-daemon",
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

            unauth_result = unauth_client.execute_action({"type": "note", "value": "hello"}, dry_run=False)
            auth_result = auth_client.execute_action({"type": "note", "value": "hello"}, dry_run=False)
        finally:
            daemon.shutdown()
            thread.join(timeout=2)

        self.assertEqual(unauth_result.status, "failed")
        self.assertIn("unauthorized", unauth_result.output)
        self.assertEqual(auth_result.status, "ok")
        self.assertIn("note:note hello", auth_result.output)


if __name__ == "__main__":
    unittest.main()
