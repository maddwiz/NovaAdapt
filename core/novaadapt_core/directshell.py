from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any


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

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or os.getenv("DIRECTSHELL_BIN", "directshell")

    def execute_action(self, action: dict[str, Any], dry_run: bool = True) -> ExecutionResult:
        if dry_run:
            return ExecutionResult(
                action=action,
                status="preview",
                output=f"Preview only: {json.dumps(action, ensure_ascii=True)}",
            )

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

    def run_plan(self, actions: list[dict[str, Any]], dry_run: bool = True) -> list[ExecutionResult]:
        return [self.execute_action(action=action, dry_run=dry_run) for action in actions]
