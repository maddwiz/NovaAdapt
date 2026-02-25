#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

pick_free_port() {
  python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

HTTP_PORT="${NOVAADAPT_SMOKE_RUNTIME_HTTP_PORT:-$(pick_free_port)}"
HTTP_TOKEN="${NOVAADAPT_SMOKE_RUNTIME_HTTP_TOKEN:-runtime-http-smoke-token}"
DAEMON_SOCKET="${NOVAADAPT_SMOKE_RUNTIME_DAEMON_SOCKET:-/tmp/novaadapt-runtime-smoke-$$.sock}"
DAEMON_TOKEN="${NOVAADAPT_SMOKE_RUNTIME_DAEMON_TOKEN:-runtime-daemon-smoke-token}"

HTTP_PID=""
DAEMON_PID=""

cleanup() {
  if [[ -n "$DAEMON_PID" ]]; then
    if kill -0 "$DAEMON_PID" >/dev/null 2>&1; then
      kill "$DAEMON_PID" >/dev/null 2>&1 || true
      wait "$DAEMON_PID" >/dev/null 2>&1 || true
    fi
  fi
  if [[ -n "$HTTP_PID" ]]; then
    if kill -0 "$HTTP_PID" >/dev/null 2>&1; then
      kill "$HTTP_PID" >/dev/null 2>&1 || true
      wait "$HTTP_PID" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "$DAEMON_SOCKET"
}
trap cleanup EXIT

wait_for_http() {
  local url="$1"
  local token="${2:-}"
  local waited=0
  while (( waited < 180 )); do
    if [[ -n "$token" ]]; then
      if curl -fsS -H "X-DirectShell-Token: ${token}" "$url" >/dev/null 2>&1; then
        return 0
      fi
    elif curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  return 1
}

wait_for_probe_ok() {
  local transport="$1"
  local token="$2"
  local waited=0
  while (( waited < 180 )); do
    cmd=(
      python3
      -m
      novaadapt_core.cli
      directshell-check
      --transport "$transport"
      --timeout-seconds 2
    )
    if [[ "$transport" == "http" ]]; then
      cmd+=(--http-token "$token")
    else
      cmd+=(--daemon-token "$token")
    fi
    if PYTHONPATH=core:shared "${cmd[@]}" 2>/dev/null | grep -q '"ok": true'; then
      return 0
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  return 1
}

echo "Starting runtime native-http..."
PYTHONPATH=core:shared python3 -m novaadapt_core.cli native-http \
  --host 127.0.0.1 \
  --port "$HTTP_PORT" \
  --http-token "$HTTP_TOKEN" \
  >/tmp/novaadapt-runtime-http-smoke.log 2>&1 &
HTTP_PID="$!"

if ! wait_for_http "http://127.0.0.1:${HTTP_PORT}/health" "$HTTP_TOKEN"; then
  echo "Runtime native-http failed to start; see /tmp/novaadapt-runtime-http-smoke.log"
  exit 1
fi

export DIRECTSHELL_HTTP_URL="http://127.0.0.1:${HTTP_PORT}/execute"
if ! wait_for_probe_ok "http" "$HTTP_TOKEN"; then
  echo "directshell-check failed for HTTP runtime"
  exit 1
fi

PYTHONPATH=core:shared python3 - <<PY
from novaadapt_core.directshell import DirectShellClient
client = DirectShellClient(
    transport="http",
    http_url="http://127.0.0.1:${HTTP_PORT}/execute",
    http_token="${HTTP_TOKEN}",
    timeout_seconds=3,
)
result = client.execute_action({"type": "note", "value": "runtime-http-smoke"}, dry_run=False)
assert result.status == "ok", result.output
PY

echo "Starting runtime native-daemon..."
PYTHONPATH=core:shared python3 -m novaadapt_core.cli native-daemon \
  --socket "$DAEMON_SOCKET" \
  --daemon-token "$DAEMON_TOKEN" \
  >/tmp/novaadapt-runtime-daemon-smoke.log 2>&1 &
DAEMON_PID="$!"

export DIRECTSHELL_DAEMON_SOCKET="$DAEMON_SOCKET"
if ! wait_for_probe_ok "daemon" "$DAEMON_TOKEN"; then
  echo "Runtime native-daemon failed readiness probe; see /tmp/novaadapt-runtime-daemon-smoke.log"
  exit 1
fi

PYTHONPATH=core:shared python3 - <<PY
from novaadapt_core.directshell import DirectShellClient
client = DirectShellClient(
    transport="daemon",
    daemon_socket="${DAEMON_SOCKET}",
    daemon_token="${DAEMON_TOKEN}",
    timeout_seconds=3,
)
result = client.execute_action({"type": "note", "value": "runtime-daemon-smoke"}, dry_run=False)
assert result.status == "ok", result.output
PY

echo "Smoke test passed: native runtime HTTP and daemon transports are working."
