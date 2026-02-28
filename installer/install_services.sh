#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$(uname -s)" in
  Darwin)
    exec "${ROOT_DIR}/installer/install_launchd_services.sh" "$@"
    ;;
  Linux)
    exec "${ROOT_DIR}/installer/install_systemd_services.sh" "$@"
    ;;
  *)
    echo "Unsupported OS for service installer: $(uname -s)" >&2
    echo "Use installer/install_systemd_services.sh (Linux) or installer/install_launchd_services.sh (macOS)." >&2
    exit 1
    ;;
esac
