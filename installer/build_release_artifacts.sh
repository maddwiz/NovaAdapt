#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
VERSION="${1:-dev}"

mkdir -p "$DIST_DIR"
rm -f "$DIST_DIR"/SHA256SUMS

echo "[release] building bridge binary"
(
  cd "$ROOT_DIR/bridge"
  GOOS="${GOOS:-$(go env GOOS)}" GOARCH="${GOARCH:-$(go env GOARCH)}" \
    go build -o "$DIST_DIR/novaadapt-bridge-${VERSION}-$(go env GOOS)-$(go env GOARCH)" ./cmd/novaadapt-bridge
)

echo "[release] building python wheel/sdist"
python3 -m pip install --upgrade build >/dev/null
(
  cd "$ROOT_DIR"
  python3 -m build --sdist --wheel --outdir "$DIST_DIR"
)

echo "[release] packaging runtime configs"
tar -C "$ROOT_DIR" -czf "$DIST_DIR/novaadapt-runtime-${VERSION}.tar.gz" deploy config docs installer

(
  cd "$DIST_DIR"
  shasum -a 256 * > SHA256SUMS
)

echo "[release] artifacts ready at $DIST_DIR"
