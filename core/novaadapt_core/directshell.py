from __future__ import annotations

import json
import os
import socket
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class ExecutionResult:
    action: dict[str, Any]
    status: str
    output: str


class DirectShellClient:
    """Thin subprocess adapter.

    This keeps the integration explicit and deterministic while allowing dry-runs
    during early MVP development.
    """

    def __init__(
        self,
        binary: str | None = None,
        transport: str | None = None,
        http_url: str | None = None,
        daemon_socket: str | None = None,
        daemon_host: str | None = None,
        daemon_port: int | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.binary = binary or os.getenv("DIRECTSHELL_BIN", "directshell")
        self.transport = (transport or os.getenv("DIRECTSHELL_TRANSPORT", "subprocess")).lower()
        self.http_url = http_url or os.getenv("DIRECTSHELL_HTTP_URL", "http://127.0.0.1:8765/execute")
        self.daemon_socket = (
            os.getenv("DIRECTSHELL_DAEMON_SOCKET", "/tmp/directshell.sock")
            if daemon_socket is None
            else daemon_socket
        )
        self.daemon_host = daemon_host or os.getenv("DIRECTSHELL_DAEMON_HOST", "127.0.0.1")
        self.daemon_port = int(os.getenv("DIRECTSHELL_DAEMON_PORT", "8766")) if daemon_port is None else int(daemon_port)
        self.timeout_seconds = timeout_seconds

    def execute_action(self, action: dict[str, Any], dry_run: bool = True) -> ExecutionResult:
        if dry_run:
            return ExecutionResult(
                action=action,
                status="preview",
                output=f"Preview only: {json.dumps(action, ensure_ascii=True)}",
            )

        if self.transport == "http":
            return self._execute_http(action)

        if self.transport == "daemon":
            return self._execute_daemon(action)

        if self.transport != "subprocess":
            raise RuntimeError(
                f"Unsupported DirectShell transport '{self.transport}'. Use 'subprocess', 'http', or 'daemon'."
            )

        return self._execute_subprocess(action)

    def _execute_subprocess(self, action: dict[str, Any]) -> ExecutionResult:
        cmd = [self.binary, "exec", "--json", json.dumps(action, ensure_ascii=True)]
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"DirectShell binary '{self.binary}' not found. Set DIRECTSHELL_BIN or install DirectShell."
            ) from exc

        status = "ok" if completed.returncode == 0 else "failed"
        output = (completed.stdout or completed.stderr).strip()
        return ExecutionResult(action=action, status=status, output=output)

    def _execute_http(self, action: dict[str, Any]) -> ExecutionResult:
        payload = json.dumps({"action": action}).encode("utf-8")
        req = request.Request(
            url=self.http_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            return ExecutionResult(action=action, status="failed", output=f"HTTP {exc.code}: {body}")
        except error.URLError as exc:
            return ExecutionResult(action=action, status="failed", output=f"HTTP transport error: {exc.reason}")

        try:
            parsed = json.loads(raw_body)
            status = str(parsed.get("status", "ok"))
            output = str(parsed.get("output", raw_body)).strip()
            return ExecutionResult(action=action, status=status, output=output)
        except json.JSONDecodeError:
            return ExecutionResult(action=action, status="ok", output=raw_body.strip())

    def _execute_daemon(self, action: dict[str, Any]) -> ExecutionResult:
        payload = json.dumps({"action": action}, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        framed = len(payload).to_bytes(4, byteorder="big") + payload
        try:
            with self._daemon_connection() as sock:
                sock.settimeout(self.timeout_seconds)
                sock.sendall(framed)
                raw_len = self._recv_exact(sock, 4)
                size = int.from_bytes(raw_len, byteorder="big")
                if size <= 0 or size > 2 * 1024 * 1024:
                    return ExecutionResult(action=action, status="failed", output="Daemon returned invalid frame size")
                raw_body = self._recv_exact(sock, size).decode("utf-8")
        except OSError as exc:
            return ExecutionResult(action=action, status="failed", output=f"Daemon transport error: {exc}")

        try:
            parsed = json.loads(raw_body)
            status = str(parsed.get("status", "ok"))
            output = str(parsed.get("output", raw_body)).strip()
            return ExecutionResult(action=action, status=status, output=output)
        except json.JSONDecodeError:
            return ExecutionResult(action=action, status="failed", output=f"Daemon returned non-JSON response: {raw_body}")

    def _daemon_connection(self):
        socket_path = str(self.daemon_socket or "").strip()
        if socket_path:
            unix_supported = hasattr(socket, "AF_UNIX")
            if not unix_supported:
                raise RuntimeError("DIRECTSHELL_DAEMON_SOCKET requires Unix domain socket support")
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(socket_path)
            except Exception:
                sock.close()
                raise
            return sock
        return socket.create_connection((self.daemon_host, self.daemon_port), timeout=self.timeout_seconds)

    @staticmethod
    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        remaining = int(size)
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = sock.recv(remaining)
            if not chunk:
                raise OSError("connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def run_plan(self, actions: list[dict[str, Any]], dry_run: bool = True) -> list[ExecutionResult]:
        return [self.execute_action(action=action, dry_run=dry_run) for action in actions]
