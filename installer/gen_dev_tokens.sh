#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$ROOT_DIR/deploy"
OUT_FILE="$DEPLOY_DIR/.env"

random_token() {
  python3 - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
}

CORE_TOKEN="${NOVAADAPT_CORE_TOKEN:-$(random_token)}"
BRIDGE_TOKEN="${NOVAADAPT_BRIDGE_TOKEN:-$(random_token)}"

cat > "$OUT_FILE" <<EOF_ENV
NOVAADAPT_CORE_TOKEN=${CORE_TOKEN}
NOVAADAPT_BRIDGE_TOKEN=${BRIDGE_TOKEN}
EOF_ENV

echo "Wrote tokens to $OUT_FILE"
