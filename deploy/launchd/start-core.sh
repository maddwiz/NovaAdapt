#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${NOVAADAPT_REPO_ROOT:-}" ]]; then
  if [[ -d "${PWD}/core/novaadapt_core" ]]; then
    NOVAADAPT_REPO_ROOT="${PWD}"
  elif [[ -d "${SCRIPT_DIR}/../../core/novaadapt_core" ]]; then
    NOVAADAPT_REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  else
    NOVAADAPT_REPO_ROOT="${PWD}"
  fi
fi

DEFAULT_PYTHON="${NOVAADAPT_REPO_ROOT}/.venv/bin/python"
if [[ ! -x "${DEFAULT_PYTHON}" ]]; then
  DEFAULT_PYTHON="$(command -v python3)"
fi

: "${NOVAADAPT_CORE_PYTHON:=${DEFAULT_PYTHON}}"
: "${NOVAADAPT_MODEL_CONFIG:=${NOVAADAPT_REPO_ROOT}/config/models.local.json}"
: "${NOVAADAPT_CORE_HOST:=127.0.0.1}"
: "${NOVAADAPT_CORE_PORT:=8787}"
: "${NOVAADAPT_CORE_JOBS_DB:=${HOME}/Library/Application Support/NovaAdapt/data/jobs.db}"
: "${NOVAADAPT_CORE_PLANS_DB:=${HOME}/Library/Application Support/NovaAdapt/data/plans.db}"
: "${NOVAADAPT_CORE_IDEMPOTENCY_DB:=${HOME}/Library/Application Support/NovaAdapt/data/idempotency.db}"
: "${NOVAADAPT_CORE_AUDIT_DB:=${HOME}/Library/Application Support/NovaAdapt/data/events.db}"
: "${NOVAADAPT_CORE_RATE_LIMIT_RPS:=20}"
: "${NOVAADAPT_CORE_RATE_LIMIT_BURST:=20}"
: "${NOVAADAPT_CORE_MAX_BODY_BYTES:=1048576}"
: "${NOVAADAPT_CORE_LOG_REQUESTS:=1}"

mkdir -p "$(dirname "${NOVAADAPT_CORE_JOBS_DB}")"
export PYTHONPATH="${NOVAADAPT_REPO_ROOT}/core:${NOVAADAPT_REPO_ROOT}/shared:${PYTHONPATH:-}"

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
if [[ "${NOVAADAPT_CORE_LOG_REQUESTS}" == "1" || "${NOVAADAPT_CORE_LOG_REQUESTS}" == "true" ]]; then
  cmd+=(--log-requests)
fi
if [[ -n "${NOVAADAPT_CORE_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${NOVAADAPT_CORE_EXTRA_ARGS})
  cmd+=("${extra_args[@]}")
fi

exec "${cmd[@]}"
