#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLAY_DIR="$ROOT_DIR/mobile/android/play-store"
DIST_DIR="$ROOT_DIR/dist"
STAMP="${1:-$(date +%Y%m%d-%H%M%S)}"
OUT_DIR="$DIST_DIR/novaadapt-play-store-kit-$STAMP"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
cp -R "$PLAY_DIR" "$OUT_DIR/play-store"

for candidate in \
  "$ROOT_DIR/mobile/android/NovaAdaptOperatorApp/app/build/outputs/apk/debug/app-debug.apk" \
  "$ROOT_DIR/mobile/android/NovaAdaptOperatorApp/app/build/outputs/apk/release/app-release.apk" \
  "$ROOT_DIR/mobile/android/NovaAdaptOperatorApp/app/build/outputs/bundle/release/app-release.aab"
do
  if [ -f "$candidate" ]; then
    cp "$candidate" "$OUT_DIR/"
  fi
done

(
  cd "$DIST_DIR"
  zip -qry "novaadapt-play-store-kit-$STAMP.zip" "novaadapt-play-store-kit-$STAMP"
)

echo "$DIST_DIR/novaadapt-play-store-kit-$STAMP.zip"
