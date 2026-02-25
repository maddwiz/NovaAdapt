#!/usr/bin/env bash
set -euo pipefail

: "${NOVAADAPT_RUNTIME_PYTHON:=/opt/novaadapt/.venv/bin/python}"
: "${NOVAADAPT_RUNTIME_MODE:=native-http}"
: "${NOVAADAPT_RUNTIME_TIMEOUT_SECONDS:=30}"

mode="$(echo "${NOVAADAPT_RUNTIME_MODE}" | tr '[:upper:]' '[:lower:]')"
cmd=()

if [[ "${mode}" == "native-http" || "${mode}" == "http" ]]; then
  : "${NOVAADAPT_RUNTIME_HTTP_HOST:=127.0.0.1}"
  : "${NOVAADAPT_RUNTIME_HTTP_PORT:=8765}"
  : "${NOVAADAPT_RUNTIME_HTTP_TOKEN:=}"
  : "${NOVAADAPT_RUNTIME_MAX_BODY_BYTES:=1048576}"

  cmd=(
    "${NOVAADAPT_RUNTIME_PYTHON}"
    -m
    novaadapt_core.cli
    native-http
    --host "${NOVAADAPT_RUNTIME_HTTP_HOST}"
    --port "${NOVAADAPT_RUNTIME_HTTP_PORT}"
    --timeout-seconds "${NOVAADAPT_RUNTIME_TIMEOUT_SECONDS}"
    --max-body-bytes "${NOVAADAPT_RUNTIME_MAX_BODY_BYTES}"
  )
  if [[ -n "${NOVAADAPT_RUNTIME_HTTP_TOKEN}" ]]; then
    cmd+=(--http-token "${NOVAADAPT_RUNTIME_HTTP_TOKEN}")
  fi
elif [[ "${mode}" == "native-daemon" || "${mode}" == "daemon" ]]; then
  : "${NOVAADAPT_RUNTIME_DAEMON_SOCKET:=/run/novaadapt/directshell.sock}"
  : "${NOVAADAPT_RUNTIME_DAEMON_HOST:=127.0.0.1}"
  : "${NOVAADAPT_RUNTIME_DAEMON_PORT:=8766}"
  : "${NOVAADAPT_RUNTIME_DAEMON_TOKEN:=}"

  if [[ -n "${NOVAADAPT_RUNTIME_DAEMON_SOCKET}" ]]; then
    mkdir -p "$(dirname "${NOVAADAPT_RUNTIME_DAEMON_SOCKET}")"
  fi

  cmd=(
    "${NOVAADAPT_RUNTIME_PYTHON}"
    -m
    novaadapt_core.cli
    native-daemon
    --socket "${NOVAADAPT_RUNTIME_DAEMON_SOCKET}"
    --host "${NOVAADAPT_RUNTIME_DAEMON_HOST}"
    --port "${NOVAADAPT_RUNTIME_DAEMON_PORT}"
    --timeout-seconds "${NOVAADAPT_RUNTIME_TIMEOUT_SECONDS}"
  )
  if [[ -n "${NOVAADAPT_RUNTIME_DAEMON_TOKEN}" ]]; then
    cmd+=(--daemon-token "${NOVAADAPT_RUNTIME_DAEMON_TOKEN}")
  fi
else
  echo "NOVAADAPT_RUNTIME_MODE must be one of: native-http, http, native-daemon, daemon" >&2
  echo "Got: ${NOVAADAPT_RUNTIME_MODE}" >&2
  exit 1
fi

if [[ -n "${NOVAADAPT_RUNTIME_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${NOVAADAPT_RUNTIME_EXTRA_ARGS})
  cmd+=("${extra_args[@]}")
fi

exec "${cmd[@]}"
