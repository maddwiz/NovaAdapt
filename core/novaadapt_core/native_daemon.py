from __future__ import annotations

import json
import os
import socket
import socketserver
from dataclasses import dataclass
from typing import Any

from .native_executor import NativeDesktopExecutor


_MAX_FRAME_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class NativeDaemonTarget:
    socket_path: str
    host: str
    port: int


class NativeExecutionDaemon:
    """Length-prefixed JSON daemon backed by NativeDesktopExecutor.

    Request frame:
      4-byte big-endian length + JSON body
      body shape: {"action": {...}}

    Response frame:
      4-byte big-endian length + JSON body
      body shape: {"status": "ok|failed", "output": "..."}
    """

    def __init__(
        self,
        *,
        socket_path: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8766,
        timeout_seconds: int = 30,
        executor: NativeDesktopExecutor | None = None,
    ) -> None:
        self.target = NativeDaemonTarget(
            socket_path=str(socket_path or ""),
            host=str(host or "127.0.0.1"),
            port=int(port),
        )
        self.executor = executor or NativeDesktopExecutor(timeout_seconds=timeout_seconds)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._server: socketserver.BaseServer | None = None

    def serve_forever(self) -> None:
        server = self._create_server()
        self._server = server
        try:
            server.serve_forever()
        finally:
            server.server_close()
            self._server = None
            if self.target.socket_path:
                try:
                    os.unlink(self.target.socket_path)
                except FileNotFoundError:
                    pass

    def shutdown(self) -> None:
        server = self._server
        if server is not None:
            server.shutdown()

    def _create_server(self) -> socketserver.BaseServer:
        handler = self._build_handler()
        socket_path = self.target.socket_path.strip()
        if socket_path:
            if not hasattr(socket, "AF_UNIX"):
                raise RuntimeError("Unix sockets are not supported on this platform")
            os.makedirs(os.path.dirname(socket_path) or ".", exist_ok=True)
            try:
                os.unlink(socket_path)
            except FileNotFoundError:
                pass
            server = _ThreadingUnixStreamServer(socket_path, handler)
            server.timeout = self.timeout_seconds
            return server
        server = _ThreadingTCPServer((self.target.host, self.target.port), handler)
        server.timeout = self.timeout_seconds
        return server

    def _build_handler(self):
        executor = self.executor

        class _Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                self.connection.settimeout(self.server.timeout)
                raw_len = self.rfile.read(4)
                if len(raw_len) != 4:
                    return
                size = int.from_bytes(raw_len, byteorder="big")
                if size <= 0 or size > _MAX_FRAME_BYTES:
                    self._write_response({"status": "failed", "output": "invalid frame size"})
                    return
                raw_body = self.rfile.read(size)
                if len(raw_body) != size:
                    self._write_response({"status": "failed", "output": "truncated frame"})
                    return

                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    self._write_response({"status": "failed", "output": f"invalid json: {exc}"})
                    return

                action = payload.get("action") if isinstance(payload, dict) else None
                if not isinstance(action, dict):
                    self._write_response({"status": "failed", "output": "payload must include object field 'action'"})
                    return

                result = executor.execute_action(action)
                self._write_response({"status": str(result.status), "output": str(result.output)})

            def _write_response(self, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
                frame = len(body).to_bytes(4, byteorder="big") + body
                self.wfile.write(frame)

        return _Handler


class _ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class _ThreadingUnixStreamServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True
