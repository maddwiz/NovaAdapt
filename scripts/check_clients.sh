#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[clients] checking desktop web shell syntax"
node --check "$ROOT_DIR/desktop/tauri-shell/src/main.js"

echo "[clients] checking desktop tauri rust crate"
cargo check --manifest-path "$ROOT_DIR/desktop/tauri-shell/src-tauri/Cargo.toml"

if command -v xcrun >/dev/null 2>&1; then
  SDK_PATH="$(xcrun --sdk iphonesimulator --show-sdk-path)"
  if [[ -n "$SDK_PATH" ]]; then
    echo "[clients] typechecking iOS companion sources"
    swiftc \
      -typecheck \
      -sdk "$SDK_PATH" \
      -target arm64-apple-ios17.0-simulator \
      "$ROOT_DIR"/mobile/ios/NovaAdaptCompanion/*.swift
  fi
else
  echo "[clients] xcrun unavailable; skipping iOS Swift typecheck"
fi

echo "[clients] checks completed"
