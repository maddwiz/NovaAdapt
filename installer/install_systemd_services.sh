#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: sudo ./installer/install_systemd_services.sh [--start]

Installs NovaAdapt systemd units and startup wrappers from the current repo.
By default this script:
  - creates novaadapt system user/group (if missing)
  - creates /etc/novaadapt and /var/lib/novaadapt
  - installs systemd unit files to /etc/systemd/system
  - copies env example files if env files do not already exist
  - reloads systemd daemon

If --start is provided, services are also enabled and started.
EOF
  exit 0
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "This script must run as root (use sudo)." >&2
  exit 1
fi

START_SERVICES=0
if [[ "${1:-}" == "--start" ]]; then
  START_SERVICES=1
elif [[ -n "${1:-}" ]]; then
  echo "Unknown argument: ${1}" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_SRC="${ROOT_DIR}/deploy/systemd"

if [[ ! -d "${SYSTEMD_SRC}" ]]; then
  echo "Missing systemd deployment directory: ${SYSTEMD_SRC}" >&2
  exit 1
fi

if ! id -u novaadapt >/dev/null 2>&1; then
  useradd --system --home /opt/novaadapt --shell /usr/sbin/nologin novaadapt
fi

mkdir -p /etc/novaadapt /var/lib/novaadapt
mkdir -p /opt/novaadapt/deploy/systemd
chown -R novaadapt:novaadapt /var/lib/novaadapt
chown -R novaadapt:novaadapt /opt/novaadapt

install -m 755 "${SYSTEMD_SRC}/start-core.sh" /opt/novaadapt/deploy/systemd/start-core.sh
install -m 755 "${SYSTEMD_SRC}/start-bridge.sh" /opt/novaadapt/deploy/systemd/start-bridge.sh

install -m 644 "${SYSTEMD_SRC}/novaadapt-core.service" /etc/systemd/system/novaadapt-core.service
install -m 644 "${SYSTEMD_SRC}/novaadapt-bridge.service" /etc/systemd/system/novaadapt-bridge.service

if [[ ! -f /etc/novaadapt/core.env ]]; then
  install -m 600 "${SYSTEMD_SRC}/core.env.example" /etc/novaadapt/core.env
fi
if [[ ! -f /etc/novaadapt/bridge.env ]]; then
  install -m 600 "${SYSTEMD_SRC}/bridge.env.example" /etc/novaadapt/bridge.env
fi

systemctl daemon-reload

if [[ "${START_SERVICES}" -eq 1 ]]; then
  systemctl enable --now novaadapt-core.service
  systemctl enable --now novaadapt-bridge.service
  echo "NovaAdapt core and bridge services are enabled and started."
else
  echo "Installed systemd units and env files."
  echo "Edit /etc/novaadapt/core.env and /etc/novaadapt/bridge.env, then run:"
  echo "  sudo systemctl enable --now novaadapt-core.service"
  echo "  sudo systemctl enable --now novaadapt-bridge.service"
fi
