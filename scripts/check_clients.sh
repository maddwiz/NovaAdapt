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

ANDROID_ROOT="$ROOT_DIR/mobile/android/NovaAdaptOperatorApp"
if [[ -d "$ANDROID_ROOT" ]]; then
  echo "[clients] verifying Android shell project files"
  test -f "$ANDROID_ROOT/settings.gradle"
  test -f "$ANDROID_ROOT/build.gradle"
  test -f "$ANDROID_ROOT/app/build.gradle"
  test -f "$ANDROID_ROOT/gradlew"
  test -f "$ANDROID_ROOT/gradlew.bat"
  test -f "$ANDROID_ROOT/gradle/wrapper/gradle-wrapper.jar"
  test -f "$ANDROID_ROOT/gradle/wrapper/gradle-wrapper.properties"
  test -f "$ANDROID_ROOT/app/src/main/java/com/novaadapt/operator/MainActivity.java"
  test -f "$ANDROID_ROOT/app/src/main/java/com/novaadapt/operator/SettingsActivity.java"
  test -f "$ANDROID_ROOT/app/src/main/java/com/novaadapt/operator/BridgeConfigStore.java"
  if command -v xmllint >/dev/null 2>&1; then
    echo "[clients] validating Android XML resources"
    find "$ANDROID_ROOT/app/src/main" -type f \( -name '*.xml' -o -name '*.manifest' \) -print0 | \
      while IFS= read -r -d '' file; do
        xmllint --noout "$file"
      done
  else
    echo "[clients] xmllint unavailable; skipping Android XML validation"
  fi
fi

echo "[clients] checks completed"
