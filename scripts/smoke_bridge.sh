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

CORE_PORT="${NOVAADAPT_SMOKE_CORE_PORT:-$(pick_free_port)}"
BRIDGE_PORT="${NOVAADAPT_SMOKE_BRIDGE_PORT:-$(pick_free_port)}"
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

for _ in {1..80}; do
  if ! kill -0 "$CORE_PID" >/dev/null 2>&1; then
    echo "Core failed to start; see /tmp/novaadapt-core-smoke.log"
    exit 1
  fi
  if curl -s "http://127.0.0.1:${CORE_PORT}/health" | python3 -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(0 if data.get("ok") else 1)' >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

./bridge/bin/novaadapt-bridge \
  --host 127.0.0.1 \
  --port "$BRIDGE_PORT" \
  --core-url "http://127.0.0.1:${CORE_PORT}" \
  --bridge-token "$BRIDGE_TOKEN" \
  --core-token "$CORE_TOKEN" \
  --log-requests=true \
  > /tmp/novaadapt-bridge-smoke.log 2>&1 &
BRIDGE_PID=$!

for _ in {1..80}; do
  if ! kill -0 "$BRIDGE_PID" >/dev/null 2>&1; then
    echo "Bridge failed to start; see /tmp/novaadapt-bridge-smoke.log"
    exit 1
  fi
  if curl -s "http://127.0.0.1:${BRIDGE_PORT}/health?deep=1" | python3 -c 'import json,sys; data=json.load(sys.stdin); raise SystemExit(0 if data.get("ok") else 1)' >/dev/null 2>&1; then
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
echo "$openapi_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("openapi")=="3.1.0"; assert "/run" in data.get("paths", {}); assert "/plans/{id}/approve" in data.get("paths", {})'

dashboard_data=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/dashboard/data")
echo "$dashboard_data" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("health", {}).get("ok") is True'

plans_json=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/plans?limit=5")
echo "$plans_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data,list)'

missing_plan_status=$(curl -s -o /tmp/novaadapt-smoke-plan-missing.json -w "%{http_code}" \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"execute":false}' \
  "http://127.0.0.1:${BRIDGE_PORT}/plans/missing-plan-id/approve")
if [[ "$missing_plan_status" != "400" ]]; then
  echo "Expected 400 from missing plan approve, got $missing_plan_status"
  exit 1
fi

missing_plan_async_status=$(curl -s -o /tmp/novaadapt-smoke-plan-missing-async.json -w "%{http_code}" \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"execute":true}' \
  "http://127.0.0.1:${BRIDGE_PORT}/plans/missing-plan-id/approve_async")
if [[ "$missing_plan_async_status" != "202" ]]; then
  echo "Expected 202 from missing plan approve_async, got $missing_plan_async_status"
  exit 1
fi
missing_async_job_id=$(python3 -c 'import json; data=json.load(open("/tmp/novaadapt-smoke-plan-missing-async.json")); print(data["job_id"])')
missing_async_job=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/jobs/${missing_async_job_id}")
echo "$missing_async_job" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert "status" in data'

missing_plan_undo_status=$(curl -s -o /tmp/novaadapt-smoke-plan-missing-undo.json -w "%{http_code}" \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"mark_only":true}' \
  "http://127.0.0.1:${BRIDGE_PORT}/plans/missing-plan-id/undo")
if [[ "$missing_plan_undo_status" != "400" ]]; then
  echo "Expected 400 from missing plan undo, got $missing_plan_undo_status"
  exit 1
fi

missing_plan_stream_status=$(curl -s -o /tmp/novaadapt-smoke-plan-missing-stream.json -w "%{http_code}" \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/plans/missing-plan-id/stream?timeout=1&interval=0.1")
if [[ "$missing_plan_stream_status" != "404" ]]; then
  echo "Expected 404 from missing plan stream, got $missing_plan_stream_status"
  exit 1
fi

idem_key="smoke-idem-run-1"
queued_job=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "Idempotency-Key: ${idem_key}" \
  -H "Content-Type: application/json" \
  -d '{"objective":"Smoke test objective"}' \
  "http://127.0.0.1:${BRIDGE_PORT}/run_async")
job_id=$(echo "$queued_job" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["job_id"])')
queued_job_replay=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "Idempotency-Key: ${idem_key}" \
  -H "Content-Type: application/json" \
  -d '{"objective":"Smoke test objective"}' \
  "http://127.0.0.1:${BRIDGE_PORT}/run_async")
job_id_replay=$(echo "$queued_job_replay" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["job_id"])')
if [[ "$job_id" != "$job_id_replay" ]]; then
  echo "Expected idempotent replay job_id match, got $job_id vs $job_id_replay"
  exit 1
fi

cancel_result=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "http://127.0.0.1:${BRIDGE_PORT}/jobs/${job_id}/cancel")
echo "$cancel_result" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert "id" in data'

stream_result=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/jobs/${job_id}/stream?timeout=2&interval=0.1")
echo "$stream_result" | grep -q 'event:'

events_json=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/events?limit=20")
echo "$events_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data,list) and len(data)>=1'

latest_event_id=$(echo "$events_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data[0]["id"])')
events_stream=$(curl -sS \
  -H "Authorization: Bearer ${BRIDGE_TOKEN}" \
  "http://127.0.0.1:${BRIDGE_PORT}/events/stream?timeout=1&interval=0.1&since_id=${latest_event_id}")
echo "$events_stream" | grep -q 'event: timeout'

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
