#!/usr/bin/env bash
set -euo pipefail

: "${NOVAADAPT_CORE_PYTHON:=/opt/novaadapt/.venv/bin/python}"
: "${NOVAADAPT_MODEL_CONFIG:=/etc/novaadapt/models.local.json}"
: "${NOVAADAPT_CORE_HOST:=127.0.0.1}"
: "${NOVAADAPT_CORE_PORT:=8787}"
: "${NOVAADAPT_CORE_JOBS_DB:=/var/lib/novaadapt/jobs.db}"
: "${NOVAADAPT_CORE_PLANS_DB:=/var/lib/novaadapt/plans.db}"
: "${NOVAADAPT_CORE_IDEMPOTENCY_DB:=/var/lib/novaadapt/idempotency.db}"
: "${NOVAADAPT_CORE_AUDIT_DB:=/var/lib/novaadapt/events.db}"
: "${NOVAADAPT_CORE_RATE_LIMIT_RPS:=20}"
: "${NOVAADAPT_CORE_RATE_LIMIT_BURST:=20}"
: "${NOVAADAPT_CORE_MAX_BODY_BYTES:=1048576}"
: "${NOVAADAPT_CORE_LOG_REQUESTS:=1}"
: "${NOVAADAPT_OTEL_ENABLED:=0}"
: "${NOVAADAPT_OTEL_SERVICE_NAME:=novaadapt-core}"

cmd=(
  "$NOVAADAPT_CORE_PYTHON"
  -m
  novaadapt_core.cli
  serve
  --config "$NOVAADAPT_MODEL_CONFIG"
  --host "$NOVAADAPT_CORE_HOST"
  --port "$NOVAADAPT_CORE_PORT"
  --jobs-db-path "$NOVAADAPT_CORE_JOBS_DB"
  --plans-db-path "$NOVAADAPT_CORE_PLANS_DB"
  --idempotency-db-path "$NOVAADAPT_CORE_IDEMPOTENCY_DB"
  --audit-db-path "$NOVAADAPT_CORE_AUDIT_DB"
  --rate-limit-rps "$NOVAADAPT_CORE_RATE_LIMIT_RPS"
  --rate-limit-burst "$NOVAADAPT_CORE_RATE_LIMIT_BURST"
  --max-body-bytes "$NOVAADAPT_CORE_MAX_BODY_BYTES"
)

if [[ -n "${NOVAADAPT_CORE_TOKEN:-}" ]]; then
  cmd+=(--api-token "$NOVAADAPT_CORE_TOKEN")
fi
if [[ "$NOVAADAPT_CORE_LOG_REQUESTS" == "1" || "$NOVAADAPT_CORE_LOG_REQUESTS" == "true" ]]; then
  cmd+=(--log-requests)
fi
if [[ "$NOVAADAPT_OTEL_ENABLED" == "1" || "$NOVAADAPT_OTEL_ENABLED" == "true" ]]; then
  cmd+=(--otel-enabled --otel-service-name "$NOVAADAPT_OTEL_SERVICE_NAME")
  if [[ -n "${NOVAADAPT_OTEL_EXPORTER_ENDPOINT:-}" ]]; then
    cmd+=(--otel-exporter-endpoint "$NOVAADAPT_OTEL_EXPORTER_ENDPOINT")
  fi
fi
if [[ -n "${NOVAADAPT_CORE_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${NOVAADAPT_CORE_EXTRA_ARGS})
  cmd+=("${extra_args[@]}")
fi

exec "${cmd[@]}"
