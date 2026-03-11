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

echo "[release] packaging runtime bundle"
tar -C "$ROOT_DIR" -czf "$DIST_DIR/novaadapt-runtime-${VERSION}.tar.gz" \
  config \
  deploy \
  docs \
  installer \
  mobile \
  scripts \
  view \
  wearables

echo "[release] packaging Android operator PWA bundle"
"$BUILD_VENV/bin/python" - "$ROOT_DIR" "$DIST_DIR" "$VERSION" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(sys.argv[1])
dist = Path(sys.argv[2])
version = sys.argv[3]
output = dist / f"novaadapt-android-pwa-{version}.zip"
include_dirs = [
    root / "view",
    root / "mobile" / "android",
]

with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
    for base in include_dirs:
        for path in sorted(base.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root))
PY

echo "[release] packaging Android native shell source bundle"
"$BUILD_VENV/bin/python" - "$ROOT_DIR" "$DIST_DIR" "$VERSION" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(sys.argv[1])
dist = Path(sys.argv[2])
version = sys.argv[3]
output = dist / f"novaadapt-android-native-shell-{version}.zip"
include_paths = [
    root / "mobile" / "android" / "README.md",
    root / "mobile" / "android" / "release_manifest.json",
    root / "mobile" / "android" / "NovaAdaptOperatorApp",
    root / "view",
]

with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
    for source in include_paths:
        if source.is_file():
            archive.write(source, source.relative_to(root))
            continue
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root))
PY

echo "[release] packaging wearable bridge bundle"
tar -C "$ROOT_DIR" -czf "$DIST_DIR/novaadapt-wearables-${VERSION}.tar.gz" \
  wearables \
  docs/realtime_protocol.md \
  config/protocols/realtime.v1.json

(
  cd "$DIST_DIR"
  shasum -a 256 * > SHA256SUMS
)

echo "[release] artifacts ready at $DIST_DIR"
