from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .native_executor import NativeDesktopExecutor


class NativeExecutionHTTPServer:
    """Minimal DirectShell-compatible HTTP endpoint backed by native executor."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        http_token: str | None = None,
        timeout_seconds: int = 30,
        max_body_bytes: int = 1 << 20,
        executor: NativeDesktopExecutor | None = None,
    ) -> None:
        raw_token = os.getenv("DIRECTSHELL_HTTP_TOKEN", "") if http_token is None else str(http_token)
        self.http_token = raw_token.strip() or None
        self.host = str(host or "127.0.0.1")
        self.port = max(1, int(port))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_body_bytes = max(1, int(max_body_bytes))
        self.executor = executor or NativeDesktopExecutor(timeout_seconds=self.timeout_seconds)
        self._server: HTTPServer | None = None

    def serve_forever(self) -> None:
        server = HTTPServer((self.host, self.port), self._build_handler())
        server.timeout = self.timeout_seconds
        self._server = server
        try:
            server.serve_forever()
        finally:
            server.server_close()
            self._server = None

    def shutdown(self) -> None:
        server = self._server
        if server is not None:
            server.shutdown()

    def _build_handler(self):
        expected_token = self.http_token
        executor = self.executor
        max_body_bytes = self.max_body_bytes

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/health":
                    self._send_json(404, {"ok": False, "error": "not found"})
                    return
                if not self._check_auth():
                    return
                query = parse_qs(parsed.query)
                deep = (str((query.get("deep") or ["0"])[0]).strip() == "1")
                if not deep:
                    self._send_json(200, {"ok": True, "service": "novaadapt-native-http"})
                    return
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "novaadapt-native-http",
                        "transport": "http",
                        "capabilities": executor.capabilities(),
                    },
                )

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/execute":
                    self._send_json(404, {"status": "failed", "output": "not found"})
                    return
                if not self._check_auth():
                    return
                payload = self._read_json_body(max_body_bytes=max_body_bytes)
                if payload is None:
                    return
                action = payload.get("action") if isinstance(payload, dict) else None
                if not isinstance(action, dict):
                    self._send_json(400, {"status": "failed", "output": "payload must include object field 'action'"})
                    return
                result = executor.execute_action(action)
                self._send_json(200, {"status": str(result.status), "output": str(result.output)})

            def _check_auth(self) -> bool:
                if not expected_token:
                    return True
                if str(self.headers.get("X-DirectShell-Token") or "") == expected_token:
                    return True
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return False

            def _read_json_body(self, *, max_body_bytes: int) -> dict[str, Any] | None:
                raw_len = str(self.headers.get("Content-Length") or "0").strip()
                try:
                    size = int(raw_len)
                except ValueError:
                    self._send_json(400, {"status": "failed", "output": "invalid content-length"})
                    return None
                if size < 0 or size > max_body_bytes:
                    self._send_json(413, {"status": "failed", "output": "payload too large"})
                    return None
                raw = self.rfile.read(size).decode("utf-8")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    self._send_json(400, {"status": "failed", "output": f"invalid json: {exc}"})
                    return None

            def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
                self.send_response(int(status_code))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                return

        return _Handler
