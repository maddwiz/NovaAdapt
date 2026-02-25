#!/usr/bin/env bash
set -euo pipefail

: "${NOVAADAPT_BRIDGE_BIN:=/opt/novaadapt/bridge/bin/novaadapt-bridge}"
: "${NOVAADAPT_BRIDGE_HOST:=0.0.0.0}"
: "${NOVAADAPT_BRIDGE_PORT:=9797}"
: "${NOVAADAPT_CORE_URL:=http://127.0.0.1:8787}"
: "${NOVAADAPT_CORE_CA_FILE:=}"
: "${NOVAADAPT_CORE_CLIENT_CERT_FILE:=}"
: "${NOVAADAPT_CORE_CLIENT_KEY_FILE:=}"
: "${NOVAADAPT_CORE_TLS_SERVER_NAME:=}"
: "${NOVAADAPT_CORE_TLS_INSECURE_SKIP_VERIFY:=0}"
: "${NOVAADAPT_BRIDGE_RATE_LIMIT_RPS:=20}"
: "${NOVAADAPT_BRIDGE_RATE_LIMIT_BURST:=20}"
: "${NOVAADAPT_BRIDGE_MAX_WS_CONNECTIONS:=100}"
: "${NOVAADAPT_BRIDGE_TIMEOUT:=30}"
: "${NOVAADAPT_BRIDGE_LOG_REQUESTS:=1}"
: "${NOVAADAPT_BRIDGE_SESSION_TTL_SECONDS:=900}"
: "${NOVAADAPT_BRIDGE_REVOCATION_STORE_PATH:=/var/lib/novaadapt/revoked_sessions.json}"

if [[ -z "${NOVAADAPT_BRIDGE_TOKEN:-}" ]]; then
  echo "NOVAADAPT_BRIDGE_TOKEN is required" >&2
  exit 1
fi

cmd=(
  "$NOVAADAPT_BRIDGE_BIN"
  --host "$NOVAADAPT_BRIDGE_HOST"
  --port "$NOVAADAPT_BRIDGE_PORT"
  --core-url "$NOVAADAPT_CORE_URL"
  --bridge-token "$NOVAADAPT_BRIDGE_TOKEN"
  --session-token-ttl-seconds "$NOVAADAPT_BRIDGE_SESSION_TTL_SECONDS"
  --rate-limit-rps "$NOVAADAPT_BRIDGE_RATE_LIMIT_RPS"
  --rate-limit-burst "$NOVAADAPT_BRIDGE_RATE_LIMIT_BURST"
  --max-ws-connections "$NOVAADAPT_BRIDGE_MAX_WS_CONNECTIONS"
  --timeout "$NOVAADAPT_BRIDGE_TIMEOUT"
  --revocation-store-path "$NOVAADAPT_BRIDGE_REVOCATION_STORE_PATH"
)

if [[ -n "${NOVAADAPT_CORE_TOKEN:-}" ]]; then
  cmd+=(--core-token "$NOVAADAPT_CORE_TOKEN")
fi
if [[ -n "${NOVAADAPT_CORE_CA_FILE:-}" ]]; then
  cmd+=(--core-ca-file "$NOVAADAPT_CORE_CA_FILE")
fi
if [[ -n "${NOVAADAPT_CORE_TLS_SERVER_NAME:-}" ]]; then
  cmd+=(--core-tls-server-name "$NOVAADAPT_CORE_TLS_SERVER_NAME")
fi
if [[ -n "${NOVAADAPT_CORE_CLIENT_CERT_FILE:-}" || -n "${NOVAADAPT_CORE_CLIENT_KEY_FILE:-}" ]]; then
  if [[ -z "${NOVAADAPT_CORE_CLIENT_CERT_FILE:-}" || -z "${NOVAADAPT_CORE_CLIENT_KEY_FILE:-}" ]]; then
    echo "both NOVAADAPT_CORE_CLIENT_CERT_FILE and NOVAADAPT_CORE_CLIENT_KEY_FILE are required for bridge->core mTLS" >&2
    exit 1
  fi
  cmd+=(--core-client-cert-file "$NOVAADAPT_CORE_CLIENT_CERT_FILE" --core-client-key-file "$NOVAADAPT_CORE_CLIENT_KEY_FILE")
fi
if [[ "$NOVAADAPT_CORE_TLS_INSECURE_SKIP_VERIFY" == "1" || "$NOVAADAPT_CORE_TLS_INSECURE_SKIP_VERIFY" == "true" ]]; then
  cmd+=(--core-tls-insecure-skip-verify=true)
fi
if [[ -n "${NOVAADAPT_BRIDGE_ALLOWED_DEVICE_IDS:-}" ]]; then
  cmd+=(--allowed-device-ids "$NOVAADAPT_BRIDGE_ALLOWED_DEVICE_IDS")
fi
if [[ -n "${NOVAADAPT_BRIDGE_CORS_ALLOWED_ORIGINS:-}" ]]; then
  cmd+=(--cors-allowed-origins "$NOVAADAPT_BRIDGE_CORS_ALLOWED_ORIGINS")
fi
if [[ -n "${NOVAADAPT_BRIDGE_TRUSTED_PROXY_CIDRS:-}" ]]; then
  cmd+=(--trusted-proxy-cidrs "$NOVAADAPT_BRIDGE_TRUSTED_PROXY_CIDRS")
fi
if [[ -n "${NOVAADAPT_BRIDGE_SESSION_SIGNING_KEY:-}" ]]; then
  cmd+=(--session-signing-key "$NOVAADAPT_BRIDGE_SESSION_SIGNING_KEY")
fi
if [[ -n "${NOVAADAPT_BRIDGE_TLS_CERT_FILE:-}" || -n "${NOVAADAPT_BRIDGE_TLS_KEY_FILE:-}" ]]; then
  if [[ -z "${NOVAADAPT_BRIDGE_TLS_CERT_FILE:-}" || -z "${NOVAADAPT_BRIDGE_TLS_KEY_FILE:-}" ]]; then
    echo "both NOVAADAPT_BRIDGE_TLS_CERT_FILE and NOVAADAPT_BRIDGE_TLS_KEY_FILE are required for TLS" >&2
    exit 1
  fi
  cmd+=(--tls-cert-file "$NOVAADAPT_BRIDGE_TLS_CERT_FILE" --tls-key-file "$NOVAADAPT_BRIDGE_TLS_KEY_FILE")
fi
if [[ "$NOVAADAPT_BRIDGE_LOG_REQUESTS" == "1" || "$NOVAADAPT_BRIDGE_LOG_REQUESTS" == "true" ]]; then
  cmd+=(--log-requests=true)
else
  cmd+=(--log-requests=false)
fi
if [[ -n "${NOVAADAPT_BRIDGE_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  extra_args=(${NOVAADAPT_BRIDGE_EXTRA_ARGS})
  cmd+=("${extra_args[@]}")
fi

exec "${cmd[@]}"
