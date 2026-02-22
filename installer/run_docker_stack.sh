#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/deploy"

if command -v docker >/dev/null 2>&1; then
  docker compose up --build -d
  echo "NovaAdapt stack started."
  echo "Core:   http://127.0.0.1:8787/health"
  echo "Bridge: http://127.0.0.1:9797/health"
else
  echo "Docker is required but not found in PATH."
  exit 1
fi
