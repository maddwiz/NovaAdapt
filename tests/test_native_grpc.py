import threading
import time
import unittest

from novaadapt_core.directshell import DirectShellClient
from novaadapt_core.native_executor import NativeDesktopExecutor
from novaadapt_core.native_grpc import NativeExecutionGRPCServer

try:
    import grpc  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover - exercised when grpcio is absent
    grpc = None


@unittest.skipIf(grpc is None, "grpcio is not installed")
class NativeGRPCServerTests(unittest.TestCase):
    def test_grpc_server_executes_action(self):
        server = NativeExecutionGRPCServer(
            host="127.0.0.1",
            port=0,
            timeout_seconds=5,
            executor=NativeDesktopExecutor(platform_name="plan9"),
        )
        port = server.bind()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            client = DirectShellClient(
                transport="grpc",
                grpc_target=f"127.0.0.1:{port}",
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

    def test_grpc_server_token_enforcement(self):
        server = NativeExecutionGRPCServer(
            host="127.0.0.1",
            port=0,
            grpc_token="secret-grpc",
            timeout_seconds=5,
            executor=NativeDesktopExecutor(platform_name="plan9"),
        )
        port = server.bind()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            unauth_client = DirectShellClient(
                transport="grpc",
                grpc_target=f"127.0.0.1:{port}",
                timeout_seconds=2,
            )
            auth_client = DirectShellClient(
                transport="grpc",
                grpc_target=f"127.0.0.1:{port}",
                grpc_token="secret-grpc",
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
        self.assertIn("UNAUTHENTICATED", str(unauth_probe.get("error", "")))
        self.assertEqual(unauth_result.status, "failed")
        self.assertIn("UNAUTHENTICATED", unauth_result.output)
        self.assertEqual(auth_result.status, "ok")
        self.assertIn("note:note hello", auth_result.output)


if __name__ == "__main__":
    unittest.main()
