#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CORE_PORT="${NOVAADAPT_SMOKE_CORE_PORT:-8787}"
BRIDGE_PORT="${NOVAADAPT_SMOKE_BRIDGE_PORT:-9797}"
CORE_TOKEN="${NOVAADAPT_SMOKE_CORE_TOKEN:-core-smoke-token}"
BRIDGE_TOKEN="${NOVAADAPT_SMOKE_BRIDGE_TOKEN:-bridge-smoke-token}"
RID="smoke-rid-001"

cleanup() {
  if [[ -n "${BRIDGE_PID:-}" ]]; then
    kill "$BRIDGE_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${CORE_PID:-}" ]]; then
    kill "$CORE_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

./installer/build_bridge_go.sh >/dev/null

PYTHONPATH='core:shared' python3 -m novaadapt_core.cli serve \
  --config config/models.example.json \
  --host 127.0.0.1 \
  --port "$CORE_PORT" \
  --api-token "$CORE_TOKEN" \
  --log-requests \
  --rate-limit-rps 20 \
  --rate-limit-burst 20 \
  --max-body-bytes 1048576 \
  > /tmp/novaadapt-core-smoke.log 2>&1 &
CORE_PID=$!

./bridge/bin/novaadapt-bridge \
  --host 127.0.0.1 \
  --port "$BRIDGE_PORT" \
  --core-url "http://127.0.0.1:${CORE_PORT}" \
  --bridge-token "$BRIDGE_TOKEN" \
  --core-token "$CORE_TOKEN" \
  --log-requests=true \
  > /tmp/novaadapt-bridge-smoke.log 2>&1 &
BRIDGE_PID=$!

for _ in {1..50}; do
  if curl -sS "http://127.0.0.1:${BRIDGE_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
 done

unauth_status=$(curl -s -o /tmp/novaadapt-smoke-unauth.json -w "%{http_code}" "http://127.0.0.1:${BRIDGE_PORT}/models")
if [[ "$unauth_status" != "401" ]]; then
  echo "Expected 401 from unauthenticated bridge request, got $unauth_status"
  exit 1
fi

models_json=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "X-Request-ID: ${RID}" \
  "http://127.0.0.1:${BRIDGE_PORT}/models")

echo "$models_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data,list) and len(data)>=1'

openapi_json=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/openapi.json")
echo "$openapi_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("openapi")=="3.1.0"; assert "/run" in data.get("paths", {})'

trace_header=$(curl -sS -D - -o /tmp/novaadapt-smoke-models.json \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "X-Request-ID: ${RID}" \
  "http://127.0.0.1:${BRIDGE_PORT}/models" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-request-id" {print $2}' | tail -n1)
if [[ "$trace_header" != "$RID" ]]; then
  echo "Expected X-Request-ID=$RID but got '$trace_header'"
  exit 1
fi

deep_health=$(curl -sS "http://127.0.0.1:${BRIDGE_PORT}/health?deep=1")
echo "$deep_health" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("ok") is True; assert "core" in data'

bridge_metrics=$(curl -sS "http://127.0.0.1:${BRIDGE_PORT}/metrics")
echo "$bridge_metrics" | grep -q 'novaadapt_bridge_requests_total'

core_metrics=$(curl -sS -H "Authorization: Bearer ${CORE_TOKEN}" "http://127.0.0.1:${CORE_PORT}/metrics")
echo "$core_metrics" | grep -q 'novaadapt_core_requests_total'

echo "Smoke test passed: bridge/core auth, tracing, and metrics are working."
