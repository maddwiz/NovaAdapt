from __future__ import annotations

import json
import os
import socket
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from .native_executor import NativeDesktopExecutor


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
        native_fallback_transport: str | None = None,
        native_executor: NativeDesktopExecutor | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.binary = binary or os.getenv("DIRECTSHELL_BIN", "directshell")
        self.transport = (transport or os.getenv("DIRECTSHELL_TRANSPORT", "native")).lower()
        self.http_url = http_url or os.getenv("DIRECTSHELL_HTTP_URL", "http://127.0.0.1:8765/execute")
        self.daemon_socket = (
            os.getenv("DIRECTSHELL_DAEMON_SOCKET", "/tmp/directshell.sock")
            if daemon_socket is None
            else daemon_socket
        )
        self.daemon_host = daemon_host or os.getenv("DIRECTSHELL_DAEMON_HOST", "127.0.0.1")
        self.daemon_port = int(os.getenv("DIRECTSHELL_DAEMON_PORT", "8766")) if daemon_port is None else int(daemon_port)
        raw_fallback = (
            os.getenv("DIRECTSHELL_NATIVE_FALLBACK_TRANSPORT", "")
            if native_fallback_transport is None
            else str(native_fallback_transport)
        )
        fallback = raw_fallback.strip().lower()
        self.native_fallback_transport = fallback or None
        if self.native_fallback_transport == "native":
            self.native_fallback_transport = None
        self.timeout_seconds = timeout_seconds
        self.native_executor = native_executor or NativeDesktopExecutor(timeout_seconds=timeout_seconds)
        self._supported_transports = {"native", "subprocess", "http", "daemon"}
        if self.transport not in self._supported_transports:
            raise RuntimeError(
                f"Unsupported DirectShell transport '{self.transport}'. "
                "Use 'native', 'subprocess', 'http', or 'daemon'."
            )
        if self.native_fallback_transport and self.native_fallback_transport not in self._supported_transports:
            raise RuntimeError(
                f"Unsupported DirectShell native fallback transport '{self.native_fallback_transport}'. "
                "Use 'subprocess', 'http', or 'daemon'."
            )

    def execute_action(self, action: dict[str, Any], dry_run: bool = True) -> ExecutionResult:
        if dry_run:
            return ExecutionResult(
                action=action,
                status="preview",
                output=f"Preview only: {json.dumps(action, ensure_ascii=True)}",
            )
        primary = self._execute_with_transport(self.transport, action)
        if (
            self.transport == "native"
            and self.native_fallback_transport
            and str(primary.status).lower() != "ok"
        ):
            fallback = self._execute_with_transport(self.native_fallback_transport, action)
            if str(fallback.status).lower() == "ok":
                output = str(fallback.output or "").strip()
                native_error = str(primary.output or "").strip()
                if native_error:
                    output = f"{output} (native fallback after: {native_error})".strip()
                return ExecutionResult(action=action, status=fallback.status, output=output)
            return ExecutionResult(
                action=action,
                status="failed",
                output=(
                    f"Native execution failed: {primary.output}; "
                    f"fallback '{self.native_fallback_transport}' failed: {fallback.output}"
                ),
            )
        return primary

    def probe(self) -> dict[str, Any]:
        transport = self.transport
        if transport == "native":
            native_probe = self._probe_native()
            if not self.native_fallback_transport:
                return native_probe
            fallback_probe = self._probe_transport(self.native_fallback_transport)
            probe = dict(native_probe)
            probe["fallback_transport"] = self.native_fallback_transport
            probe["fallback_probe"] = fallback_probe
            probe["ok"] = bool(native_probe.get("ok")) or bool(fallback_probe.get("ok"))
            return probe
        if transport == "http":
            return self._probe_http()
        if transport == "daemon":
            return self._probe_daemon()
        if transport == "subprocess":
            return self._probe_subprocess()
        return {
            "ok": False,
            "transport": transport,
            "error": "unsupported transport",
            "supported_transports": ["native", "subprocess", "http", "daemon"],
        }

    def _probe_transport(self, transport: str) -> dict[str, Any]:
        if transport == "native":
            return self._probe_native()
        if transport == "subprocess":
            return self._probe_subprocess()
        if transport == "http":
            return self._probe_http()
        if transport == "daemon":
            return self._probe_daemon()
        return {
            "ok": False,
            "transport": transport,
            "error": "unsupported transport",
        }

    def _execute_with_transport(self, transport: str, action: dict[str, Any]) -> ExecutionResult:
        if transport == "native":
            return self._execute_native(action)
        if transport == "subprocess":
            return self._execute_subprocess(action)
        if transport == "http":
            return self._execute_http(action)
        if transport == "daemon":
            return self._execute_daemon(action)
        raise RuntimeError(
            f"Unsupported DirectShell transport '{transport}'. Use 'native', 'subprocess', 'http', or 'daemon'."
        )

    def _execute_native(self, action: dict[str, Any]) -> ExecutionResult:
        result = self.native_executor.execute_action(action)
        return ExecutionResult(
            action=action,
            status=str(result.status),
            output=str(result.output),
        )

    def _probe_native(self) -> dict[str, Any]:
        return self.native_executor.probe()

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

    def _probe_subprocess(self) -> dict[str, Any]:
        cmd = [self.binary, "--help"]
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "transport": "subprocess",
                "binary": self.binary,
                "error": f"DirectShell binary '{self.binary}' not found",
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "transport": "subprocess",
                "binary": self.binary,
                "error": f"DirectShell binary probe timed out after {self.timeout_seconds}s",
            }

        output = (completed.stdout or completed.stderr or "").strip()
        return {
            "ok": completed.returncode in {0, 1, 2},
            "transport": "subprocess",
            "binary": self.binary,
            "returncode": completed.returncode,
            "output": output,
        }

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

    def _probe_http(self) -> dict[str, Any]:
        parsed = urlparse(self.http_url)
        if not parsed.scheme or not parsed.netloc:
            return {
                "ok": False,
                "transport": "http",
                "url": self.http_url,
                "error": "invalid DIRECTSHELL_HTTP_URL",
            }

        health_url = f"{parsed.scheme}://{parsed.netloc}/health"
        req = request.Request(url=health_url, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return {
                    "ok": True,
                    "transport": "http",
                    "url": self.http_url,
                    "health_url": health_url,
                    "status_code": int(response.status),
                }
        except error.HTTPError as exc:
            reachable = int(exc.code) < 500
            return {
                "ok": reachable,
                "transport": "http",
                "url": self.http_url,
                "health_url": health_url,
                "status_code": int(exc.code),
                "error": f"HTTP {exc.code}",
            }
        except error.URLError as exc:
            return {
                "ok": False,
                "transport": "http",
                "url": self.http_url,
                "health_url": health_url,
                "error": f"HTTP transport error: {exc.reason}",
            }

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

    def _probe_daemon(self) -> dict[str, Any]:
        target = (
            {"socket": str(self.daemon_socket or "").strip()}
            if str(self.daemon_socket or "").strip()
            else {"host": self.daemon_host, "port": self.daemon_port}
        )
        try:
            with self._daemon_connection() as sock:
                sock.settimeout(self.timeout_seconds)
            return {
                "ok": True,
                "transport": "daemon",
                **target,
            }
        except OSError as exc:
            return {
                "ok": False,
                "transport": "daemon",
                "error": f"Daemon transport error: {exc}",
                **target,
            }

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
