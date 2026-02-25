#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_ENV_DEFAULT="/etc/novaadapt/core.env"
BRIDGE_ENV_DEFAULT="/etc/novaadapt/bridge.env"
DOCKER_ENV_DEFAULT="$ROOT_DIR/deploy/.env"

core_env="$CORE_ENV_DEFAULT"
bridge_env="$BRIDGE_ENV_DEFAULT"
docker_env="$DOCKER_ENV_DEFAULT"
restart_services=0
dry_run=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Rotate NovaAdapt core/bridge tokens in env files.

Options:
  --core-env PATH       Core env file (default: $CORE_ENV_DEFAULT)
  --bridge-env PATH     Bridge env file (default: $BRIDGE_ENV_DEFAULT)
  --docker-env PATH     Docker env file (default: $DOCKER_ENV_DEFAULT)
  --restart-systemd     Restart novaadapt-core and novaadapt-bridge services
  --dry-run             Print planned values and files without writing
  -h, --help            Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --core-env)
      core_env="$2"
      shift 2
      ;;
    --bridge-env)
      bridge_env="$2"
      shift 2
      ;;
    --docker-env)
      docker_env="$2"
      shift 2
      ;;
    --restart-systemd)
      restart_services=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

random_token() {
  python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
}

core_token="${NOVAADAPT_CORE_TOKEN:-$(random_token)}"
bridge_token="${NOVAADAPT_BRIDGE_TOKEN:-$(random_token)}"

upsert_kv() {
  local file="$1"
  local key="$2"
  local value="$3"

  mkdir -p "$(dirname "$file")"
  [[ -f "$file" ]] || touch "$file"

  if grep -qE "^${key}=" "$file"; then
    sed -i.bak -E "s|^${key}=.*$|${key}=${value}|" "$file"
    rm -f "${file}.bak"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

if [[ "$dry_run" == "1" ]]; then
  echo "[dry-run] would write:"
  echo "  $core_env  NOVAADAPT_CORE_TOKEN=<redacted>"
  echo "  $bridge_env  NOVAADAPT_BRIDGE_TOKEN=<redacted>"
  echo "  $docker_env  NOVAADAPT_CORE_TOKEN=<redacted>"
  echo "  $docker_env  NOVAADAPT_BRIDGE_TOKEN=<redacted>"
  if [[ "$restart_services" == "1" ]]; then
    echo "[dry-run] would restart systemd services: novaadapt-core, novaadapt-bridge"
  fi
  exit 0
fi

upsert_kv "$core_env" "NOVAADAPT_CORE_TOKEN" "$core_token"
upsert_kv "$bridge_env" "NOVAADAPT_BRIDGE_TOKEN" "$bridge_token"
upsert_kv "$docker_env" "NOVAADAPT_CORE_TOKEN" "$core_token"
upsert_kv "$docker_env" "NOVAADAPT_BRIDGE_TOKEN" "$bridge_token"

echo "Updated token files:"
echo "  $core_env"
echo "  $bridge_env"
echo "  $docker_env"

if [[ "$restart_services" == "1" ]]; then
  echo "Restarting systemd services..."
  sudo systemctl restart novaadapt-core.service
  sudo systemctl restart novaadapt-bridge.service
  echo "Services restarted"
fi

cat <<DONE

Token rotation complete.
Recommended follow-up:
  1) Reissue scoped bridge sessions.
  2) Reconnect mobile/wearable clients.
DONE
