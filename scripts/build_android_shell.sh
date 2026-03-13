#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/mobile/android/NovaAdaptOperatorApp"
ANDROID_SDK_DEFAULT="/opt/homebrew/share/android-commandlinetools"
JAVA_HOME_DEFAULT="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
KEYSTORE_DIR_DEFAULT="$HOME/.novaadapt/android"
SIGNING_ENV_DEFAULT="$KEYSTORE_DIR_DEFAULT/novaadapt-operator-signing.env"

MODE="all"
GENERATE_KEYSTORE=1
KEYSTORE_DIR="${NOVAADAPT_ANDROID_KEYSTORE_DIR:-$KEYSTORE_DIR_DEFAULT}"
SIGNING_ENV_FILE="${NOVAADAPT_ANDROID_SIGNING_ENV:-$SIGNING_ENV_DEFAULT}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    debug|release|bundle|all|test|verify)
      MODE="$1"
      ;;
    --no-generate-keystore)
      GENERATE_KEYSTORE=0
      ;;
    --generate-keystore)
      GENERATE_KEYSTORE=1
      ;;
    --keystore-dir)
      KEYSTORE_DIR="$2"
      SIGNING_ENV_FILE="$KEYSTORE_DIR/novaadapt-operator-signing.env"
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

export JAVA_HOME="${JAVA_HOME:-$JAVA_HOME_DEFAULT}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$ANDROID_SDK_DEFAULT}}"
export PATH="$JAVA_HOME/bin:/opt/homebrew/bin:$PATH"

if [[ ! -x "$APP_DIR/gradlew" ]]; then
  echo "gradle wrapper missing at $APP_DIR/gradlew" >&2
  exit 1
fi

if [[ ! -d "$ANDROID_SDK_ROOT/platforms/android-35" ]]; then
  echo "Android SDK platform android-35 not found at $ANDROID_SDK_ROOT" >&2
  exit 1
fi

load_signing_env() {
  if [[ -f "$SIGNING_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$SIGNING_ENV_FILE"
  fi
}

write_signing_env() {
  mkdir -p "$KEYSTORE_DIR"
  umask 077
  cat > "$SIGNING_ENV_FILE" <<ENV
export NOVAADAPT_ANDROID_KEYSTORE_PATH='$NOVAADAPT_ANDROID_KEYSTORE_PATH'
export NOVAADAPT_ANDROID_KEYSTORE_PASSWORD='$NOVAADAPT_ANDROID_KEYSTORE_PASSWORD'
export NOVAADAPT_ANDROID_KEY_ALIAS='$NOVAADAPT_ANDROID_KEY_ALIAS'
export NOVAADAPT_ANDROID_KEY_PASSWORD='$NOVAADAPT_ANDROID_KEY_PASSWORD'
ENV
}

ensure_keystore() {
  load_signing_env
  if [[ -n "${NOVAADAPT_ANDROID_KEYSTORE_PATH:-}" && -f "${NOVAADAPT_ANDROID_KEYSTORE_PATH}" ]]; then
    return 0
  fi
  if [[ "$GENERATE_KEYSTORE" -ne 1 ]]; then
    echo "release signing is not configured and auto-generation is disabled" >&2
    exit 1
  fi
  mkdir -p "$KEYSTORE_DIR"
  export NOVAADAPT_ANDROID_KEYSTORE_PATH="$KEYSTORE_DIR/novaadapt-operator-upload.jks"
  export NOVAADAPT_ANDROID_KEYSTORE_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
  export NOVAADAPT_ANDROID_KEY_ALIAS="novaadapt-upload"
  export NOVAADAPT_ANDROID_KEY_PASSWORD="$NOVAADAPT_ANDROID_KEYSTORE_PASSWORD"
  keytool -genkeypair \
    -storetype PKCS12 \
    -keystore "$NOVAADAPT_ANDROID_KEYSTORE_PATH" \
    -storepass "$NOVAADAPT_ANDROID_KEYSTORE_PASSWORD" \
    -keypass "$NOVAADAPT_ANDROID_KEY_PASSWORD" \
    -alias "$NOVAADAPT_ANDROID_KEY_ALIAS" \
    -keyalg RSA \
    -keysize 4096 \
    -validity 3650 \
    -dname "CN=NovaAdapt Operator, OU=NovaAdapt, O=NovaAdapt, L=Remote, ST=Remote, C=US"
  write_signing_env
  echo "generated Android upload keystore at $NOVAADAPT_ANDROID_KEYSTORE_PATH"
  echo "signing environment stored at $SIGNING_ENV_FILE"
}

cd "$APP_DIR"
chmod +x ./gradlew

case "$MODE" in
  debug)
    ./gradlew assembleDebug --console=plain
    ;;
  test)
    ./gradlew testDebugUnitTest --console=plain
    ;;
  verify)
    ./gradlew testDebugUnitTest assembleDebug --console=plain
    ;;
  release)
    ensure_keystore
    ./gradlew assembleRelease --console=plain
    ;;
  bundle)
    ensure_keystore
    ./gradlew bundleRelease --console=plain
    ;;
  all)
    ./gradlew assembleDebug --console=plain
    ensure_keystore
    ./gradlew assembleRelease bundleRelease --console=plain
    ;;
  *)
    echo "unsupported mode: $MODE" >&2
    exit 1
    ;;
esac

printf '\nArtifacts:\n'
find "$APP_DIR/app/build/outputs" -type f \( -name '*.apk' -o -name '*.aab' \) | sort
