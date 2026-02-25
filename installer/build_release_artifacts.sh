#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
VERSION="${1:-dev}"
TARGET_GOOS="${GOOS:-$(go env GOOS)}"
TARGET_GOARCH="${GOARCH:-$(go env GOARCH)}"
BUILD_VENV="$(mktemp -d)"
PKG_BUILD_DIR="$ROOT_DIR/build"

cleanup() {
  rm -rf "$BUILD_VENV"
  rm -rf "$PKG_BUILD_DIR"
  find "$ROOT_DIR" -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +
}
trap cleanup EXIT

mkdir -p "$DIST_DIR"
rm -f "$DIST_DIR"/SHA256SUMS
rm -rf "$PKG_BUILD_DIR"
find "$ROOT_DIR" -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +

echo "[release] building bridge binary"
(
  cd "$ROOT_DIR/bridge"
  GOOS="$TARGET_GOOS" GOARCH="$TARGET_GOARCH" \
    go build -o "$DIST_DIR/novaadapt-bridge-${VERSION}-${TARGET_GOOS}-${TARGET_GOARCH}" ./cmd/novaadapt-bridge
)

echo "[release] building python wheel/sdist"
python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip build >/dev/null
(
  cd "$ROOT_DIR"
  "$BUILD_VENV/bin/python" -m build --sdist --wheel --outdir "$DIST_DIR"
)

echo "[release] packaging runtime configs"
tar -C "$ROOT_DIR" -czf "$DIST_DIR/novaadapt-runtime-${VERSION}.tar.gz" deploy config docs installer

(
  cd "$DIST_DIR"
  shasum -a 256 * > SHA256SUMS
)

echo "[release] artifacts ready at $DIST_DIR"
