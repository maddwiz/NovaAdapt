#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE_DIR="$ROOT_DIR/bridge"
OUT_DIR="$BRIDGE_DIR/bin"

if ! command -v go >/dev/null 2>&1; then
  echo "Go is required to build the bridge binary. Install Go and retry."
  exit 1
fi

mkdir -p "$OUT_DIR"
cd "$BRIDGE_DIR"
go test ./...
go build -o "$OUT_DIR/novaadapt-bridge" ./cmd/novaadapt-bridge

echo "Built bridge binary at: $OUT_DIR/novaadapt-bridge"
