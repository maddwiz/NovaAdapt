import json
import os
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

from novaadapt_core.memory.spine_backend import NoopMemoryBackend, NovaSpineHTTPMemoryBackend


class _MemoryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/v1/health":
            self._send(200, {"status": "ok"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        _ = json.loads(raw) if raw else {}
        if self.path == "/api/v1/memory/augment":
            self._send(200, {"context": "<relevant-memories><user>dark mode</user></relevant-memories>"})
            return
        if self.path == "/api/v1/memory/recall":
            self._send(
                200,
                {
                    "memories": [
                        {
                            "content": "Use dark mode",
                            "score": 0.9,
                            "role": "user",
                            "session_id": "s1",
                            "metadata": {"source": "test"},
                        }
                    ]
                },
            )
            return
        if self.path == "/api/v1/memory/ingest":
            self._send(200, {"chunk_ids": ["c1"], "count": 1})
            return
        self._send(404, {"error": "not found"})

    def _send(self, status: int, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


@contextmanager
def _patched_env(name: str, value: str):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


class MemoryBackendTests(unittest.TestCase):
    def test_noop_backend(self):
        backend = NoopMemoryBackend()
        self.assertTrue(backend.status()["ok"])
        self.assertFalse(backend.status()["enabled"])
        self.assertEqual(backend.recall("prefs"), [])
        self.assertEqual(backend.augment("prefs"), "")
        self.assertIsNone(backend.ingest("hello"))

    def test_http_backend_unavailable_is_optional_by_default(self):
        backend = NovaSpineHTTPMemoryBackend(base_url="http://127.0.0.1:9", timeout_seconds=0.1, retry_after_seconds=1)
        status = backend.status()
        self.assertTrue(status["ok"])
        self.assertFalse(status["enabled"])
        self.assertFalse(status["reachable"])

    def test_http_backend_unavailable_can_be_required(self):
        with _patched_env("NOVAADAPT_MEMORY_REQUIRED", "1"):
            backend = NovaSpineHTTPMemoryBackend(base_url="http://127.0.0.1:9", timeout_seconds=0.1, retry_after_seconds=1)
            status = backend.status()
            self.assertFalse(status["ok"])
            self.assertFalse(status["enabled"])
            self.assertFalse(status["reachable"])
            self.assertTrue(status["required"])

    def test_http_backend_roundtrip(self):
        server = HTTPServer(("127.0.0.1", 0), _MemoryHandler)
        host, port = server.server_address
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            backend = NovaSpineHTTPMemoryBackend(
                base_url=f"http://{host}:{port}",
                timeout_seconds=1.0,
                retry_after_seconds=1,
            )
            status = backend.status()
            self.assertTrue(status["ok"])
            self.assertTrue(status["enabled"])
            self.assertTrue(status["reachable"])

            context = backend.augment("dark mode")
            self.assertIn("relevant-memories", context)

            memories = backend.recall("preferences", top_k=3)
            self.assertEqual(len(memories), 1)
            self.assertEqual(memories[0]["role"], "user")

            ingested = backend.ingest("User likes dark mode", source_id="run-1", metadata={"test": True})
            self.assertIsNotNone(ingested)
            self.assertEqual(ingested["count"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

