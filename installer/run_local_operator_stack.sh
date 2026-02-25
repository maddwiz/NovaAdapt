#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CORE_HOST="${NOVAADAPT_CORE_HOST:-127.0.0.1}"
CORE_PORT="${NOVAADAPT_CORE_PORT:-8787}"
BRIDGE_HOST="${NOVAADAPT_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${NOVAADAPT_BRIDGE_PORT:-9797}"
VIEW_PORT="${NOVAADAPT_VIEW_PORT:-8088}"
MODEL_CONFIG="${NOVAADAPT_MODEL_CONFIG:-config/models.example.json}"
WITH_VIEW="${NOVAADAPT_WITH_VIEW:-1}"
ALLOWED_DEVICE_IDS="${NOVAADAPT_BRIDGE_ALLOWED_DEVICE_IDS:-}"
CORS_ALLOWED_ORIGINS="${NOVAADAPT_BRIDGE_CORS_ALLOWED_ORIGINS:-}"
LOG_DIR="${NOVAADAPT_LOCAL_LOG_DIR:-$ROOT_DIR/.novaadapt-local}"
mkdir -p "$LOG_DIR"

if [[ -z "$CORS_ALLOWED_ORIGINS" && "$WITH_VIEW" == "1" ]]; then
  CORS_ALLOWED_ORIGINS="http://127.0.0.1:${VIEW_PORT}"
fi

random_token() {
  python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
}

CORE_TOKEN="${NOVAADAPT_CORE_TOKEN:-$(random_token)}"
BRIDGE_TOKEN="${NOVAADAPT_BRIDGE_TOKEN:-$(random_token)}"

CORE_PID=""
BRIDGE_PID=""
VIEW_PID=""

cleanup() {
  if [[ -n "$VIEW_PID" ]]; then kill "$VIEW_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "$BRIDGE_PID" ]]; then kill "$BRIDGE_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "$CORE_PID" ]]; then kill "$CORE_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

wait_for_http() {
  local url="$1"
  local timeout="${2:-12}"
  local waited=0
  while (( waited < timeout * 10 )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  return 1
}

echo "Building bridge binary..."
./installer/build_bridge_go.sh >/dev/null

echo "Starting core API..."
PYTHONPATH=core:shared python3 -m novaadapt_core.cli serve \
  --config "$MODEL_CONFIG" \
  --host "$CORE_HOST" \
  --port "$CORE_PORT" \
  --api-token "$CORE_TOKEN" \
  --log-requests \
  >"$LOG_DIR/core.log" 2>&1 &
CORE_PID="$!"

if ! wait_for_http "http://${CORE_HOST}:${CORE_PORT}/health" 18; then
  echo "Core failed to start. Check $LOG_DIR/core.log"
  exit 1
fi

echo "Starting bridge..."
bridge_cmd=(
  ./bridge/bin/novaadapt-bridge
  --host "$BRIDGE_HOST"
  --port "$BRIDGE_PORT"
  --core-url "http://${CORE_HOST}:${CORE_PORT}"
  --bridge-token "$BRIDGE_TOKEN"
  --core-token "$CORE_TOKEN"
  --log-requests=true
)
if [[ -n "$ALLOWED_DEVICE_IDS" ]]; then
  bridge_cmd+=(--allowed-device-ids "$ALLOWED_DEVICE_IDS")
fi
if [[ -n "$CORS_ALLOWED_ORIGINS" ]]; then
  bridge_cmd+=(--cors-allowed-origins "$CORS_ALLOWED_ORIGINS")
fi
"${bridge_cmd[@]}" >"$LOG_DIR/bridge.log" 2>&1 &
BRIDGE_PID="$!"

if ! wait_for_http "http://${BRIDGE_HOST}:${BRIDGE_PORT}/health?deep=1" 18; then
  echo "Bridge failed to start. Check $LOG_DIR/bridge.log"
  exit 1
fi

if [[ "$WITH_VIEW" == "1" ]]; then
  echo "Starting view static server..."
  (
    cd "$ROOT_DIR/view"
    python3 -m http.server "$VIEW_PORT"
  ) >"$LOG_DIR/view.log" 2>&1 &
  VIEW_PID="$!"
fi

echo ""
echo "NovaAdapt local operator stack is running."
echo "Core health:      http://${CORE_HOST}:${CORE_PORT}/health"
echo "Core dashboard:   http://${CORE_HOST}:${CORE_PORT}/dashboard?token=${CORE_TOKEN}"
echo "Bridge health:    http://${BRIDGE_HOST}:${BRIDGE_PORT}/health?deep=1"
echo "Bridge websocket: ws://${BRIDGE_HOST}:${BRIDGE_PORT}/ws?token=${BRIDGE_TOKEN}"
if [[ "$WITH_VIEW" == "1" ]]; then
  echo "View console:     http://127.0.0.1:${VIEW_PORT}/realtime_console.html"
fi
echo ""
echo "Core token:       ${CORE_TOKEN}"
echo "Bridge token:     ${BRIDGE_TOKEN}"
if [[ -n "$ALLOWED_DEVICE_IDS" ]]; then
  echo "Allowed devices:  ${ALLOWED_DEVICE_IDS}"
fi
if [[ -n "$CORS_ALLOWED_ORIGINS" ]]; then
  echo "CORS origins:     ${CORS_ALLOWED_ORIGINS}"
fi
echo ""
echo "Logs:"
echo "  $LOG_DIR/core.log"
echo "  $LOG_DIR/bridge.log"
if [[ "$WITH_VIEW" == "1" ]]; then
  echo "  $LOG_DIR/view.log"
fi
echo ""
echo "Press Ctrl+C to stop."

while true; do
  if [[ -n "$CORE_PID" ]] && ! kill -0 "$CORE_PID" >/dev/null 2>&1; then
    echo "Core process exited unexpectedly. Check $LOG_DIR/core.log"
    exit 1
  fi
  if [[ -n "$BRIDGE_PID" ]] && ! kill -0 "$BRIDGE_PID" >/dev/null 2>&1; then
    echo "Bridge process exited unexpectedly. Check $LOG_DIR/bridge.log"
    exit 1
  fi
  if [[ -n "$VIEW_PID" ]] && ! kill -0 "$VIEW_PID" >/dev/null 2>&1; then
    echo "View server exited unexpectedly. Check $LOG_DIR/view.log"
    exit 1
  fi
  sleep 1
done
