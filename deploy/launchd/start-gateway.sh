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

: "${NOVAADAPT_GATEWAY_PYTHON:=${DEFAULT_PYTHON}}"
: "${NOVAADAPT_MODEL_CONFIG:=${NOVAADAPT_REPO_ROOT}/config/models.local.json}"
: "${NOVAADAPT_GATEWAY_DB:=${HOME}/Library/Application Support/NovaAdapt/data/gateway.db}"
: "${NOVAADAPT_CORE_DB:=}"
: "${NOVAADAPT_CORE_PLANS_DB:=${HOME}/Library/Application Support/NovaAdapt/data/plans.db}"
: "${NOVAADAPT_CORE_AUDIT_DB:=${HOME}/Library/Application Support/NovaAdapt/data/events.db}"
: "${NOVAADAPT_GATEWAY_POLL_INTERVAL_SECONDS:=0.25}"
: "${NOVAADAPT_GATEWAY_RETRY_DELAY_SECONDS:=10}"
: "${NOVAADAPT_GATEWAY_MAX_ATTEMPTS:=3}"
: "${NOVAADAPT_GATEWAY_DEFAULT_WORKSPACE:=default}"
: "${NOVAADAPT_GATEWAY_DEFAULT_PROFILE:=unleashed_local}"
: "${NOVAADAPT_GATEWAY_CHANNEL_WORKSPACE_MAP:=}"
: "${NOVAADAPT_GATEWAY_CHANNEL_PROFILE_MAP:=}"

mkdir -p "$(dirname "${NOVAADAPT_GATEWAY_DB}")"
export PYTHONPATH="${NOVAADAPT_REPO_ROOT}/core:${NOVAADAPT_REPO_ROOT}/shared:${PYTHONPATH:-}"

cmd=(
  "$NOVAADAPT_GATEWAY_PYTHON"
  -m
  novaadapt_core.cli
  gateway-daemon
  --config "$NOVAADAPT_MODEL_CONFIG"
  --plans-db-path "$NOVAADAPT_CORE_PLANS_DB"
  --audit-db-path "$NOVAADAPT_CORE_AUDIT_DB"
  --gateway-db-path "$NOVAADAPT_GATEWAY_DB"
  --poll-interval-seconds "$NOVAADAPT_GATEWAY_POLL_INTERVAL_SECONDS"
  --retry-delay-seconds "$NOVAADAPT_GATEWAY_RETRY_DELAY_SECONDS"
  --max-attempts "$NOVAADAPT_GATEWAY_MAX_ATTEMPTS"
  --default-workspace "$NOVAADAPT_GATEWAY_DEFAULT_WORKSPACE"
  --default-profile "$NOVAADAPT_GATEWAY_DEFAULT_PROFILE"
)

if [[ -n "${NOVAADAPT_CORE_DB:-}" ]]; then
  cmd+=(--db-path "$NOVAADAPT_CORE_DB")
fi
if [[ -n "${NOVAADAPT_GATEWAY_CHANNEL_WORKSPACE_MAP:-}" ]]; then
  cmd+=(--channel-workspace-map "$NOVAADAPT_GATEWAY_CHANNEL_WORKSPACE_MAP")
fi
if [[ -n "${NOVAADAPT_GATEWAY_CHANNEL_PROFILE_MAP:-}" ]]; then
  cmd+=(--channel-profile-map "$NOVAADAPT_GATEWAY_CHANNEL_PROFILE_MAP")
fi
if [[ -n "${NOVAADAPT_GATEWAY_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${NOVAADAPT_GATEWAY_EXTRA_ARGS})
  cmd+=("${extra_args[@]}")
fi

exec "${cmd[@]}"
