#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TextIO
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT_DIR / "core"
SHARED_DIR = ROOT_DIR / "shared"

for _path in (str(CORE_DIR), str(SHARED_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from novaadapt_core.directshell import DirectShellClient  # noqa: E402


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def merged_pythonpath(existing: str | None) -> str:
    parts = [str(CORE_DIR), str(SHARED_DIR)]
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def wait_for_http(url: str, token: str, timeout_seconds: float = 18.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        req = request.Request(url=url, method="GET", headers={"X-DirectShell-Token": token})
        try:
            with request.urlopen(req, timeout=1.0) as resp:
                if 200 <= int(resp.status) < 400:
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def run_probe(transport: str, token: str, env: dict[str, str], timeout_seconds: float = 20.0) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "novaadapt_core.cli",
        "directshell-check",
        "--transport",
        transport,
        "--timeout-seconds",
        "2",
    ]
    if transport == "http":
        cmd.extend(["--http-token", token])
    elif transport == "daemon":
        cmd.extend(["--daemon-token", token])
    try:
        completed = subprocess.run(
            cmd,
            cwd=ROOT_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"{transport} probe timed out"

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    ok = completed.returncode == 0 and '"ok": true' in output.lower()
    return ok, output


def terminate_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def tail_text(path: Path, max_lines: int = 40) -> str:
    if not path.exists():
        return "<log file not found>"
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform smoke test for native runtime HTTP+daemon transports")
    parser.add_argument("--http-port", type=int, default=int(os.getenv("NOVAADAPT_SMOKE_RUNTIME_HTTP_PORT", "0") or "0"))
    parser.add_argument("--http-token", default=os.getenv("NOVAADAPT_SMOKE_RUNTIME_HTTP_TOKEN", "runtime-http-smoke-token"))
    parser.add_argument(
        "--daemon-host",
        default=os.getenv("NOVAADAPT_SMOKE_RUNTIME_DAEMON_HOST", "127.0.0.1"),
    )
    parser.add_argument("--daemon-port", type=int, default=int(os.getenv("NOVAADAPT_SMOKE_RUNTIME_DAEMON_PORT", "0") or "0"))
    parser.add_argument(
        "--daemon-token",
        default=os.getenv("NOVAADAPT_SMOKE_RUNTIME_DAEMON_TOKEN", "runtime-daemon-smoke-token"),
    )
    args = parser.parse_args()

    http_port = int(args.http_port or pick_free_port())
    daemon_port = int(args.daemon_port or pick_free_port())

    base_env = dict(os.environ)
    base_env["PYTHONPATH"] = merged_pythonpath(base_env.get("PYTHONPATH"))

    log_dir = Path(tempfile.gettempdir())
    http_log_path = log_dir / "novaadapt-runtime-http-smoke.log"
    daemon_log_path = log_dir / "novaadapt-runtime-daemon-smoke.log"

    http_log: TextIO | None = None
    daemon_log: TextIO | None = None
    http_proc: subprocess.Popen[str] | None = None
    daemon_proc: subprocess.Popen[str] | None = None

    try:
        print("Starting runtime native-http...", flush=True)
        http_log = http_log_path.open("w", encoding="utf-8")
        http_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "novaadapt_core.cli",
                "native-http",
                "--host",
                "127.0.0.1",
                "--port",
                str(http_port),
                "--http-token",
                str(args.http_token),
            ],
            cwd=ROOT_DIR,
            env=base_env,
            stdout=http_log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        if not wait_for_http(f"http://127.0.0.1:{http_port}/health", str(args.http_token)):
            print(f"Runtime native-http failed to start; see {http_log_path}", file=sys.stderr)
            print(tail_text(http_log_path), file=sys.stderr)
            return 1

        http_env = dict(base_env)
        http_env["DIRECTSHELL_HTTP_URL"] = f"http://127.0.0.1:{http_port}/execute"
        http_env["DIRECTSHELL_HTTP_TOKEN"] = str(args.http_token)
        ok, probe_out = run_probe("http", str(args.http_token), env=http_env)
        if not ok:
            print("directshell-check failed for HTTP runtime", file=sys.stderr)
            print(probe_out, file=sys.stderr)
            return 1

        http_client = DirectShellClient(
            transport="http",
            http_url=f"http://127.0.0.1:{http_port}/execute",
            http_token=str(args.http_token),
            timeout_seconds=3,
        )
        http_result = http_client.execute_action({"type": "note", "value": "runtime-http-smoke"}, dry_run=False)
        if str(http_result.status).lower() != "ok":
            print(f"HTTP runtime execute failed: {http_result.output}", file=sys.stderr)
            return 1

        print("Starting runtime native-daemon...", flush=True)
        daemon_log = daemon_log_path.open("w", encoding="utf-8")
        daemon_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "novaadapt_core.cli",
                "native-daemon",
                "--socket",
                "",
                "--host",
                str(args.daemon_host),
                "--port",
                str(daemon_port),
                "--daemon-token",
                str(args.daemon_token),
            ],
            cwd=ROOT_DIR,
            env=base_env,
            stdout=daemon_log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        daemon_env = dict(base_env)
        daemon_env["DIRECTSHELL_DAEMON_SOCKET"] = ""
        daemon_env["DIRECTSHELL_DAEMON_HOST"] = str(args.daemon_host)
        daemon_env["DIRECTSHELL_DAEMON_PORT"] = str(daemon_port)
        daemon_env["DIRECTSHELL_DAEMON_TOKEN"] = str(args.daemon_token)

        deadline = time.monotonic() + 18.0
        probe_ok = False
        probe_out = ""
        while time.monotonic() < deadline:
            probe_ok, probe_out = run_probe("daemon", str(args.daemon_token), env=daemon_env)
            if probe_ok:
                break
            time.sleep(0.1)
        if not probe_ok:
            print(f"Runtime native-daemon failed readiness probe; see {daemon_log_path}", file=sys.stderr)
            print(probe_out, file=sys.stderr)
            print(tail_text(daemon_log_path), file=sys.stderr)
            return 1

        daemon_client = DirectShellClient(
            transport="daemon",
            daemon_socket="",
            daemon_host=str(args.daemon_host),
            daemon_port=daemon_port,
            daemon_token=str(args.daemon_token),
            timeout_seconds=3,
        )
        daemon_result = daemon_client.execute_action({"type": "note", "value": "runtime-daemon-smoke"}, dry_run=False)
        if str(daemon_result.status).lower() != "ok":
            print(f"Daemon runtime execute failed: {daemon_result.output}", file=sys.stderr)
            return 1

        print("Smoke test passed: native runtime HTTP and daemon transports are working.")
        return 0

    except KeyboardInterrupt:
        return 130
    except error.URLError as exc:
        print(f"Smoke test transport error: {exc}", file=sys.stderr)
        return 1
    finally:
        terminate_process(daemon_proc)
        terminate_process(http_proc)
        if daemon_log is not None:
            daemon_log.close()
        if http_log is not None:
            http_log.close()


if __name__ == "__main__":
    raise SystemExit(main())
