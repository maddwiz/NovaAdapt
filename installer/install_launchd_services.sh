#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./installer/install_launchd_services.sh [--start] [--with-gateway]

Installs NovaAdapt launchd agents for the current macOS user.
By default this script:
  - creates ~/Library/Application Support/NovaAdapt/{launchd,env,data}
  - copies launchd startup wrappers
  - installs env files if they do not already exist
  - renders launchd plists to ~/Library/LaunchAgents

Flags:
  --start         bootstrap core + bridge agents after install
  --with-gateway  also bootstrap gateway agent
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "install_launchd_services.sh is only supported on macOS." >&2
  exit 1
fi
if [[ "${EUID}" -eq 0 ]]; then
  echo "Do not run this script with sudo. Install launchd services as the target user." >&2
  exit 1
fi

START_SERVICES=0
WITH_GATEWAY=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --start)
      START_SERVICES=1
      ;;
    --with-gateway)
      WITH_GATEWAY=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/deploy/launchd"
if [[ ! -d "${SRC_DIR}" ]]; then
  echo "Missing launchd deployment directory: ${SRC_DIR}" >&2
  exit 1
fi

APP_SUPPORT_DIR="${HOME}/Library/Application Support/NovaAdapt"
WRAPPER_DIR="${APP_SUPPORT_DIR}/launchd"
ENV_DIR="${APP_SUPPORT_DIR}/env"
DATA_DIR="${APP_SUPPORT_DIR}/data"
LOG_DIR="${HOME}/Library/Logs/NovaAdapt"
AGENTS_DIR="${HOME}/Library/LaunchAgents"

mkdir -p "${WRAPPER_DIR}" "${ENV_DIR}" "${DATA_DIR}" "${LOG_DIR}" "${AGENTS_DIR}"

install -m 755 "${SRC_DIR}/start-core.sh" "${WRAPPER_DIR}/start-core.sh"
install -m 755 "${SRC_DIR}/start-bridge.sh" "${WRAPPER_DIR}/start-bridge.sh"
install -m 755 "${SRC_DIR}/start-gateway.sh" "${WRAPPER_DIR}/start-gateway.sh"

install_env_if_missing() {
  local source_file="$1"
  local target_file="$2"
  if [[ -f "${target_file}" ]]; then
    return
  fi
  install -m 600 "${source_file}" "${target_file}"
  local escaped_root escaped_home
  escaped_root="$(printf '%s' "${ROOT_DIR}" | sed -e 's/[&|]/\\&/g')"
  escaped_home="$(printf '%s' "${HOME}" | sed -e 's/[&|]/\\&/g')"
  sed -i '' \
    -e "s|/Users/your-user/path/to/NovaAdapt|${escaped_root}|g" \
    -e "s|/Users/your-user|${escaped_home}|g" \
    "${target_file}"
}

install_env_if_missing "${SRC_DIR}/core.env.example" "${ENV_DIR}/core.env"
install_env_if_missing "${SRC_DIR}/bridge.env.example" "${ENV_DIR}/bridge.env"
install_env_if_missing "${SRC_DIR}/gateway.env.example" "${ENV_DIR}/gateway.env"

escape_sed() {
  printf '%s' "$1" | sed -e 's/[&|]/\\&/g'
}

render_plist() {
  local template_file="$1"
  local output_file="$2"
  local env_file="$3"
  local script_file="$4"
  local workdir="$5"
  local out_log="$6"
  local err_log="$7"

  local env_escaped script_escaped workdir_escaped out_escaped err_escaped
  env_escaped="$(escape_sed "${env_file}")"
  script_escaped="$(escape_sed "${script_file}")"
  workdir_escaped="$(escape_sed "${workdir}")"
  out_escaped="$(escape_sed "${out_log}")"
  err_escaped="$(escape_sed "${err_log}")"

  sed \
    -e "s|__ENV_FILE__|${env_escaped}|g" \
    -e "s|__SCRIPT_FILE__|${script_escaped}|g" \
    -e "s|__WORKDIR__|${workdir_escaped}|g" \
    -e "s|__LOG_OUT__|${out_escaped}|g" \
    -e "s|__LOG_ERR__|${err_escaped}|g" \
    "${template_file}" > "${output_file}"
}

render_plist \
  "${SRC_DIR}/com.novaadapt.core.plist.template" \
  "${AGENTS_DIR}/com.novaadapt.core.plist" \
  "${ENV_DIR}/core.env" \
  "${WRAPPER_DIR}/start-core.sh" \
  "${ROOT_DIR}" \
  "${LOG_DIR}/core.out.log" \
  "${LOG_DIR}/core.err.log"

render_plist \
  "${SRC_DIR}/com.novaadapt.bridge.plist.template" \
  "${AGENTS_DIR}/com.novaadapt.bridge.plist" \
  "${ENV_DIR}/bridge.env" \
  "${WRAPPER_DIR}/start-bridge.sh" \
  "${ROOT_DIR}" \
  "${LOG_DIR}/bridge.out.log" \
  "${LOG_DIR}/bridge.err.log"

render_plist \
  "${SRC_DIR}/com.novaadapt.gateway.plist.template" \
  "${AGENTS_DIR}/com.novaadapt.gateway.plist" \
  "${ENV_DIR}/gateway.env" \
  "${WRAPPER_DIR}/start-gateway.sh" \
  "${ROOT_DIR}" \
  "${LOG_DIR}/gateway.out.log" \
  "${LOG_DIR}/gateway.err.log"

bootstrap_agent() {
  local label="$1"
  local plist="$2"
  launchctl bootout "gui/${UID}" "${plist}" >/dev/null 2>&1 || true
  if ! launchctl bootstrap "gui/${UID}" "${plist}" >/dev/null 2>&1; then
    launchctl load -w "${plist}"
  fi
  launchctl enable "gui/${UID}/${label}" >/dev/null 2>&1 || true
  launchctl kickstart -k "gui/${UID}/${label}" >/dev/null 2>&1 || true
}

if [[ "${START_SERVICES}" -eq 1 ]]; then
  bootstrap_agent "com.novaadapt.core" "${AGENTS_DIR}/com.novaadapt.core.plist"
  bootstrap_agent "com.novaadapt.bridge" "${AGENTS_DIR}/com.novaadapt.bridge.plist"
  if [[ "${WITH_GATEWAY}" -eq 1 ]]; then
    bootstrap_agent "com.novaadapt.gateway" "${AGENTS_DIR}/com.novaadapt.gateway.plist"
    echo "NovaAdapt core, bridge, and gateway launchd agents are installed and started."
  else
    echo "NovaAdapt core and bridge launchd agents are installed and started."
    echo "Optional gateway agent: launchctl bootstrap gui/${UID} ${AGENTS_DIR}/com.novaadapt.gateway.plist"
  fi
else
  echo "Installed launchd wrappers, env files, and plists."
  echo "Edit:"
  echo "  ${ENV_DIR}/core.env"
  echo "  ${ENV_DIR}/bridge.env"
  echo "  ${ENV_DIR}/gateway.env"
  echo "Then run:"
  echo "  launchctl bootstrap gui/${UID} ${AGENTS_DIR}/com.novaadapt.core.plist"
  echo "  launchctl bootstrap gui/${UID} ${AGENTS_DIR}/com.novaadapt.bridge.plist"
  echo "Optional gateway:"
  echo "  launchctl bootstrap gui/${UID} ${AGENTS_DIR}/com.novaadapt.gateway.plist"
fi
