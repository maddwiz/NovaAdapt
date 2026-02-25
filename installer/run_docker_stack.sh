#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/deploy"

WITH_TAILSCALE="${NOVAADAPT_WITH_TAILSCALE:-0}"
for arg in "$@"; do
  case "$arg" in
    --with-tailscale)
      WITH_TAILSCALE="1"
      ;;
    --without-tailscale)
      WITH_TAILSCALE="0"
      ;;
  esac
done

is_truthy() {
  local value
  value="$(echo "$1" | tr '[:upper:]' '[:lower:]')"
  [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

read_env_file_var() {
  local key="$1"
  local env_file=".env"
  if [[ ! -f "$env_file" ]]; then
    return 1
  fi
  local line
  line="$(grep -E "^${key}=" "$env_file" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    return 1
  fi
  echo "${line#*=}"
}

if command -v docker >/dev/null 2>&1; then
  if [[ ! -f .env ]]; then
    "$ROOT_DIR/installer/gen_dev_tokens.sh"
  fi
  compose_files=(-f docker-compose.yml)
  if is_truthy "$WITH_TAILSCALE"; then
    if [[ -z "${NOVAADAPT_TAILSCALE_AUTHKEY:-}" ]]; then
      NOVAADAPT_TAILSCALE_AUTHKEY="$(read_env_file_var NOVAADAPT_TAILSCALE_AUTHKEY || true)"
      export NOVAADAPT_TAILSCALE_AUTHKEY
    fi
    if [[ -z "${NOVAADAPT_TAILSCALE_AUTHKEY:-}" ]]; then
      echo "Tailscale is enabled but NOVAADAPT_TAILSCALE_AUTHKEY is empty."
      echo "Set NOVAADAPT_TAILSCALE_AUTHKEY in deploy/.env or shell env, then rerun."
      exit 1
    fi
    compose_files+=(-f docker-compose.tailscale.yml)
  fi

  docker compose "${compose_files[@]}" up --build -d
  echo "NovaAdapt stack started."
  echo "Core:   http://127.0.0.1:8787/health"
  echo "Bridge: http://127.0.0.1:9797/health"
  if is_truthy "$WITH_TAILSCALE"; then
    echo "Tailscale relay enabled (tailnet access to bridge container)."
  fi
else
  echo "Docker is required but not found in PATH."
  exit 1
fi
