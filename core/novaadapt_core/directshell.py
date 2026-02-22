from __future__ import annotations

import json
import os
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
        timeout_seconds: int = 30,
    ) -> None:
        self.binary = binary or os.getenv("DIRECTSHELL_BIN", "directshell")
        self.transport = (transport or os.getenv("DIRECTSHELL_TRANSPORT", "subprocess")).lower()
        self.http_url = http_url or os.getenv("DIRECTSHELL_HTTP_URL", "http://127.0.0.1:8765/execute")
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

        if self.transport != "subprocess":
            raise RuntimeError(
                f"Unsupported DirectShell transport '{self.transport}'. Use 'subprocess' or 'http'."
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

    def run_plan(self, actions: list[dict[str, Any]], dry_run: bool = True) -> list[ExecutionResult]:
        return [self.execute_action(action=action, dry_run=dry_run) for action in actions]
