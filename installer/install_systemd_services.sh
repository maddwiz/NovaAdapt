#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo ./installer/install_systemd_services.sh [--start] [--with-runtime] [--with-gateway]

Installs NovaAdapt systemd units and startup wrappers from the current repo.
By default this script:
  - creates novaadapt system user/group (if missing)
  - creates /etc/novaadapt and /var/lib/novaadapt
  - installs systemd unit files to /etc/systemd/system
  - copies env example files if env files do not already exist
  - reloads systemd daemon

Flags:
  --start         enable/start core + bridge services after install
  --with-runtime  also enable/start runtime service
                  (runtime unit/env files are installed in all cases)
                  (when combined with --start, starts novaadapt-runtime.service)
  --with-gateway  also enable/start gateway service
                  (gateway unit/env files are installed in all cases)
                  (when combined with --start, starts novaadapt-gateway.service)
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "This script must run as root (use sudo)." >&2
  exit 1
fi

START_SERVICES=0
WITH_RUNTIME=0
WITH_GATEWAY=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --start)
      START_SERVICES=1
      ;;
    --with-runtime)
      WITH_RUNTIME=1
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
install -m 755 "${SYSTEMD_SRC}/start-runtime.sh" /opt/novaadapt/deploy/systemd/start-runtime.sh
install -m 755 "${SYSTEMD_SRC}/start-gateway.sh" /opt/novaadapt/deploy/systemd/start-gateway.sh

install -m 644 "${SYSTEMD_SRC}/novaadapt-core.service" /etc/systemd/system/novaadapt-core.service
install -m 644 "${SYSTEMD_SRC}/novaadapt-bridge.service" /etc/systemd/system/novaadapt-bridge.service
install -m 644 "${SYSTEMD_SRC}/novaadapt-runtime.service" /etc/systemd/system/novaadapt-runtime.service
install -m 644 "${SYSTEMD_SRC}/novaadapt-gateway.service" /etc/systemd/system/novaadapt-gateway.service

if [[ ! -f /etc/novaadapt/core.env ]]; then
  install -m 600 "${SYSTEMD_SRC}/core.env.example" /etc/novaadapt/core.env
fi
if [[ ! -f /etc/novaadapt/bridge.env ]]; then
  install -m 600 "${SYSTEMD_SRC}/bridge.env.example" /etc/novaadapt/bridge.env
fi
if [[ ! -f /etc/novaadapt/runtime.env ]]; then
  install -m 600 "${SYSTEMD_SRC}/runtime.env.example" /etc/novaadapt/runtime.env
fi
if [[ ! -f /etc/novaadapt/gateway.env ]]; then
  install -m 600 "${SYSTEMD_SRC}/gateway.env.example" /etc/novaadapt/gateway.env
fi

systemctl daemon-reload

if [[ "${START_SERVICES}" -eq 1 ]]; then
  systemctl enable --now novaadapt-core.service
  systemctl enable --now novaadapt-bridge.service

  started_optional=0
  if [[ "${WITH_RUNTIME}" -eq 1 ]]; then
    systemctl enable --now novaadapt-runtime.service
    started_optional=1
  fi
  if [[ "${WITH_GATEWAY}" -eq 1 ]]; then
    systemctl enable --now novaadapt-gateway.service
    started_optional=1
  fi

  if [[ "${started_optional}" -eq 1 ]]; then
    echo "NovaAdapt core, bridge, and requested optional services are enabled and started."
  else
    echo "NovaAdapt core and bridge services are enabled and started."
    echo "Optional runtime service: sudo systemctl enable --now novaadapt-runtime.service"
    echo "Optional gateway service: sudo systemctl enable --now novaadapt-gateway.service"
  fi
else
  echo "Installed systemd units and env files."
  echo "Edit /etc/novaadapt/core.env and /etc/novaadapt/bridge.env, then run:"
  echo "  sudo systemctl enable --now novaadapt-core.service"
  echo "  sudo systemctl enable --now novaadapt-bridge.service"
  echo "Optional runtime service:"
  echo "  sudo editor /etc/novaadapt/runtime.env"
  echo "  sudo systemctl enable --now novaadapt-runtime.service"
  echo "Optional gateway service:"
  echo "  sudo editor /etc/novaadapt/gateway.env"
  echo "  sudo systemctl enable --now novaadapt-gateway.service"
fi
