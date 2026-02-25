#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CORE_HOST="${NOVAADAPT_CORE_HOST:-127.0.0.1}"
CORE_PORT="${NOVAADAPT_CORE_PORT:-8787}"
CORE_TRUSTED_PROXY_CIDRS="${NOVAADAPT_CORE_TRUSTED_PROXY_CIDRS:-}"
BRIDGE_HOST="${NOVAADAPT_BRIDGE_HOST:-127.0.0.1}"
BRIDGE_PORT="${NOVAADAPT_BRIDGE_PORT:-9797}"
VIEW_PORT="${NOVAADAPT_VIEW_PORT:-8088}"
MODEL_CONFIG="${NOVAADAPT_MODEL_CONFIG:-config/models.example.json}"
WITH_VIEW="${NOVAADAPT_WITH_VIEW:-1}"
CORE_CA_FILE="${NOVAADAPT_CORE_CA_FILE:-}"
CORE_CLIENT_CERT_FILE="${NOVAADAPT_CORE_CLIENT_CERT_FILE:-}"
CORE_CLIENT_KEY_FILE="${NOVAADAPT_CORE_CLIENT_KEY_FILE:-}"
CORE_TLS_SERVER_NAME="${NOVAADAPT_CORE_TLS_SERVER_NAME:-}"
CORE_TLS_INSECURE_SKIP_VERIFY="${NOVAADAPT_CORE_TLS_INSECURE_SKIP_VERIFY:-0}"
ALLOWED_DEVICE_IDS="${NOVAADAPT_BRIDGE_ALLOWED_DEVICE_IDS:-}"
CORS_ALLOWED_ORIGINS="${NOVAADAPT_BRIDGE_CORS_ALLOWED_ORIGINS:-}"
TRUSTED_PROXY_CIDRS="${NOVAADAPT_BRIDGE_TRUSTED_PROXY_CIDRS:-}"
BRIDGE_TLS_CERT_FILE="${NOVAADAPT_BRIDGE_TLS_CERT_FILE:-}"
BRIDGE_TLS_KEY_FILE="${NOVAADAPT_BRIDGE_TLS_KEY_FILE:-}"
BRIDGE_TLS_INSECURE_SKIP_VERIFY="${NOVAADAPT_BRIDGE_TLS_INSECURE_SKIP_VERIFY:-1}"
RATE_LIMIT_RPS="${NOVAADAPT_BRIDGE_RATE_LIMIT_RPS:-0}"
RATE_LIMIT_BURST="${NOVAADAPT_BRIDGE_RATE_LIMIT_BURST:-20}"
MAX_WS_CONNECTIONS="${NOVAADAPT_BRIDGE_MAX_WS_CONNECTIONS:-100}"
CORE_OTEL_ENABLED="${NOVAADAPT_OTEL_ENABLED:-0}"
CORE_OTEL_SERVICE_NAME="${NOVAADAPT_OTEL_SERVICE_NAME:-novaadapt-core}"
CORE_OTEL_EXPORTER_ENDPOINT="${NOVAADAPT_OTEL_EXPORTER_ENDPOINT:-}"
LOG_DIR="${NOVAADAPT_LOCAL_LOG_DIR:-$ROOT_DIR/.novaadapt-local}"
mkdir -p "$LOG_DIR"
REVOCATION_STORE_PATH="${NOVAADAPT_BRIDGE_REVOCATION_STORE_PATH:-$LOG_DIR/revoked_sessions.json}"

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
  local insecure_skip_verify="${3:-0}"
  local waited=0
  while (( waited < timeout * 10 )); do
    if [[ "$insecure_skip_verify" == "1" ]]; then
      if curl -k -fsS "$url" >/dev/null 2>&1; then
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

echo "Building bridge binary..."
./installer/build_bridge_go.sh >/dev/null

echo "Starting core API..."
core_cmd=(
  python3
  -m
  novaadapt_core.cli
  serve
  --config "$MODEL_CONFIG"
  --host "$CORE_HOST"
  --port "$CORE_PORT"
  --api-token "$CORE_TOKEN"
  --log-requests
)
if [[ -n "$CORE_TRUSTED_PROXY_CIDRS" ]]; then
  core_cmd+=(--trusted-proxy-cidrs "$CORE_TRUSTED_PROXY_CIDRS")
fi
if [[ "$CORE_OTEL_ENABLED" == "1" || "$CORE_OTEL_ENABLED" == "true" ]]; then
  core_cmd+=(--otel-enabled --otel-service-name "$CORE_OTEL_SERVICE_NAME")
  if [[ -n "$CORE_OTEL_EXPORTER_ENDPOINT" ]]; then
    core_cmd+=(--otel-exporter-endpoint "$CORE_OTEL_EXPORTER_ENDPOINT")
  fi
fi
PYTHONPATH=core:shared "${core_cmd[@]}" >"$LOG_DIR/core.log" 2>&1 &
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
if [[ -n "$CORE_CA_FILE" ]]; then
  bridge_cmd+=(--core-ca-file "$CORE_CA_FILE")
fi
if [[ -n "$CORE_TLS_SERVER_NAME" ]]; then
  bridge_cmd+=(--core-tls-server-name "$CORE_TLS_SERVER_NAME")
fi
if [[ -n "$CORE_CLIENT_CERT_FILE" || -n "$CORE_CLIENT_KEY_FILE" ]]; then
  if [[ -z "$CORE_CLIENT_CERT_FILE" || -z "$CORE_CLIENT_KEY_FILE" ]]; then
    echo "Both NOVAADAPT_CORE_CLIENT_CERT_FILE and NOVAADAPT_CORE_CLIENT_KEY_FILE are required for bridge->core mTLS."
    exit 1
  fi
  bridge_cmd+=(--core-client-cert-file "$CORE_CLIENT_CERT_FILE" --core-client-key-file "$CORE_CLIENT_KEY_FILE")
fi
if [[ "$CORE_TLS_INSECURE_SKIP_VERIFY" == "1" || "$CORE_TLS_INSECURE_SKIP_VERIFY" == "true" ]]; then
  bridge_cmd+=(--core-tls-insecure-skip-verify=true)
fi
if [[ -n "$CORS_ALLOWED_ORIGINS" ]]; then
  bridge_cmd+=(--cors-allowed-origins "$CORS_ALLOWED_ORIGINS")
fi
if [[ -n "$TRUSTED_PROXY_CIDRS" ]]; then
  bridge_cmd+=(--trusted-proxy-cidrs "$TRUSTED_PROXY_CIDRS")
fi
if [[ -n "$BRIDGE_TLS_CERT_FILE" || -n "$BRIDGE_TLS_KEY_FILE" ]]; then
  if [[ -z "$BRIDGE_TLS_CERT_FILE" || -z "$BRIDGE_TLS_KEY_FILE" ]]; then
    echo "Both NOVAADAPT_BRIDGE_TLS_CERT_FILE and NOVAADAPT_BRIDGE_TLS_KEY_FILE are required for TLS."
    exit 1
  fi
  bridge_cmd+=(--tls-cert-file "$BRIDGE_TLS_CERT_FILE" --tls-key-file "$BRIDGE_TLS_KEY_FILE")
fi
bridge_cmd+=(--rate-limit-rps "$RATE_LIMIT_RPS" --rate-limit-burst "$RATE_LIMIT_BURST")
bridge_cmd+=(--max-ws-connections "$MAX_WS_CONNECTIONS")
if [[ -n "$REVOCATION_STORE_PATH" ]]; then
  bridge_cmd+=(--revocation-store-path "$REVOCATION_STORE_PATH")
fi
"${bridge_cmd[@]}" >"$LOG_DIR/bridge.log" 2>&1 &
BRIDGE_PID="$!"

bridge_health_url="http://${BRIDGE_HOST}:${BRIDGE_PORT}/health?deep=1"
bridge_health_insecure="0"
if [[ -n "$BRIDGE_TLS_CERT_FILE" && -n "$BRIDGE_TLS_KEY_FILE" ]]; then
  bridge_health_url="https://${BRIDGE_HOST}:${BRIDGE_PORT}/health?deep=1"
  bridge_health_insecure="$BRIDGE_TLS_INSECURE_SKIP_VERIFY"
fi

if ! wait_for_http "$bridge_health_url" 18 "$bridge_health_insecure"; then
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
if [[ -n "$BRIDGE_TLS_CERT_FILE" && -n "$BRIDGE_TLS_KEY_FILE" ]]; then
  echo "Bridge health:    https://${BRIDGE_HOST}:${BRIDGE_PORT}/health?deep=1"
  echo "Bridge websocket: wss://${BRIDGE_HOST}:${BRIDGE_PORT}/ws?token=${BRIDGE_TOKEN}"
else
  echo "Bridge health:    http://${BRIDGE_HOST}:${BRIDGE_PORT}/health?deep=1"
  echo "Bridge websocket: ws://${BRIDGE_HOST}:${BRIDGE_PORT}/ws?token=${BRIDGE_TOKEN}"
fi
if [[ "$WITH_VIEW" == "1" ]]; then
  echo "View console:     http://127.0.0.1:${VIEW_PORT}/realtime_console.html"
fi
echo ""
echo "Core token:       ${CORE_TOKEN}"
echo "Bridge token:     ${BRIDGE_TOKEN}"
if [[ -n "$CORE_TRUSTED_PROXY_CIDRS" ]]; then
  echo "Core trusted proxies: ${CORE_TRUSTED_PROXY_CIDRS}"
fi
if [[ "$CORE_OTEL_ENABLED" == "1" || "$CORE_OTEL_ENABLED" == "true" ]]; then
  echo "Core tracing:     enabled (${CORE_OTEL_SERVICE_NAME})"
  if [[ -n "$CORE_OTEL_EXPORTER_ENDPOINT" ]]; then
    echo "OTLP endpoint:    ${CORE_OTEL_EXPORTER_ENDPOINT}"
  fi
fi
if [[ -n "$ALLOWED_DEVICE_IDS" ]]; then
  echo "Allowed devices:  ${ALLOWED_DEVICE_IDS}"
fi
if [[ -n "$CORS_ALLOWED_ORIGINS" ]]; then
  echo "CORS origins:     ${CORS_ALLOWED_ORIGINS}"
fi
if [[ -n "$TRUSTED_PROXY_CIDRS" ]]; then
  echo "Trusted proxies:  ${TRUSTED_PROXY_CIDRS}"
fi
if [[ -n "$CORE_CA_FILE" ]]; then
  echo "Core CA file:     ${CORE_CA_FILE}"
fi
if [[ -n "$CORE_CLIENT_CERT_FILE" && -n "$CORE_CLIENT_KEY_FILE" ]]; then
  echo "Core mTLS cert:   ${CORE_CLIENT_CERT_FILE}"
  echo "Core mTLS key:    ${CORE_CLIENT_KEY_FILE}"
fi
if [[ -n "$CORE_TLS_SERVER_NAME" ]]; then
  echo "Core TLS SNI:     ${CORE_TLS_SERVER_NAME}"
fi
if [[ "$CORE_TLS_INSECURE_SKIP_VERIFY" == "1" || "$CORE_TLS_INSECURE_SKIP_VERIFY" == "true" ]]; then
  echo "Core TLS verify:  disabled (unsafe)"
fi
if [[ -n "$BRIDGE_TLS_CERT_FILE" && -n "$BRIDGE_TLS_KEY_FILE" ]]; then
  echo "Bridge TLS cert:  ${BRIDGE_TLS_CERT_FILE}"
  echo "Bridge TLS key:   ${BRIDGE_TLS_KEY_FILE}"
fi
echo "Rate limit rps:   ${RATE_LIMIT_RPS}"
echo "Rate limit burst: ${RATE_LIMIT_BURST}"
echo "Max ws conns:     ${MAX_WS_CONNECTIONS}"
echo "Revocation store: ${REVOCATION_STORE_PATH}"
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
