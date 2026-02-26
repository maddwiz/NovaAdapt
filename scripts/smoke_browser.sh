#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REQUIRED="${NOVAADAPT_SMOKE_BROWSER_REQUIRED:-0}"

if ! PYTHONPATH=core:shared python3 - <<'PY'
import importlib
import sys

try:
    importlib.import_module("playwright.sync_api")
except Exception:
    sys.exit(1)
sys.exit(0)
PY
then
  if [[ "$REQUIRED" == "1" ]]; then
    echo "Browser smoke failed: Playwright is not installed. Install with: pip install -e '.[browser]'"
    exit 1
  fi
  echo "Browser smoke skipped: Playwright is not installed."
  exit 0
fi

if ! PYTHONPATH=core:shared python3 - <<'PY'
import tempfile
from pathlib import Path

from novaadapt_core.browser_executor import BrowserExecutor

with tempfile.TemporaryDirectory() as tmp:
    shot_dir = Path(tmp)
    executor = BrowserExecutor(
        headless=True,
        allowlist=["example.com"],
        screenshot_dir=shot_dir,
        timeout_seconds=20,
        default_timeout_ms=15000,
    )

    probe = executor.probe()
    if not bool(probe.get("ok")):
        raise RuntimeError(str(probe.get("error") or "browser probe failed"))

    nav = executor.execute_action({"type": "navigate", "target": "https://example.com"})
    if nav.status != "ok":
        raise RuntimeError(nav.output)

    wait = executor.execute_action({"type": "wait_for_selector", "selector": "h1", "state": "visible"})
    if wait.status != "ok":
        raise RuntimeError(wait.output)

    extract = executor.execute_action({"type": "extract_text", "selector": "h1"})
    if extract.status != "ok":
        raise RuntimeError(extract.output)

    shot = executor.execute_action({"type": "screenshot", "path": "smoke.png", "full_page": True})
    if shot.status != "ok":
        raise RuntimeError(shot.output)

    shot_path = Path(str((shot.data or {}).get("path", "")))
    if not shot_path.exists():
        raise RuntimeError(f"expected screenshot file at {shot_path}")

    close = executor.close()
    if close.status != "ok":
        raise RuntimeError(close.output)

print("Browser smoke test passed: Playwright runtime actions are working.")
PY
then
  if [[ "$REQUIRED" == "1" ]]; then
    echo "Browser smoke failed."
    exit 1
  fi
  echo "Browser smoke skipped: Playwright package is installed but browser runtime is not ready."
  exit 0
fi
