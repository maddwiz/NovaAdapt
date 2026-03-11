#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${NOVAADAPT_CONFIG_PATH:-$ROOT_DIR/config/models.example.json}"
PLATFORM="${NOVAADAPT_MOBILE_PLATFORM:-android}"
STRATEGY="${NOVAADAPT_MOBILE_STRATEGY:-single}"
MODEL="${NOVAADAPT_MOBILE_MODEL:-}"
CANDIDATES="${NOVAADAPT_MOBILE_CANDIDATES:-}"
FALLBACKS="${NOVAADAPT_MOBILE_FALLBACKS:-}"
GOAL="${NOVAADAPT_MOBILE_GOAL:-Open the banking app and prepare the next bill-pay step safely}"
ACTION_JSON="${NOVAADAPT_MOBILE_ACTION_JSON:-}"
SCREENSHOT_PATH="${1:-${NOVAADAPT_MOBILE_SCREENSHOT_PATH:-}}"
EXECUTE_FLAG="${NOVAADAPT_DEMO_EXECUTE:-0}"
ALLOW_DANGEROUS_FLAG="${NOVAADAPT_ALLOW_DANGEROUS:-0}"

if [[ -z "$ACTION_JSON" && "$PLATFORM" == "android" ]]; then
  ACTION_JSON='{"type":"open_app","target":"com.example.bank.app"}'
fi

if [[ "$PLATFORM" == "ios" && -z "$ACTION_JSON" && -z "$SCREENSHOT_PATH" ]]; then
  echo "iOS goal mode needs a screenshot path unless NOVAADAPT_MOBILE_ACTION_JSON is set." >&2
  exit 1
fi

PYTHONPATH="$ROOT_DIR/core:$ROOT_DIR/shared${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

cmd=(
  python3 -m novaadapt_core.cli mobile-action
  --config "$CONFIG_PATH"
  --platform "$PLATFORM"
  --strategy "$STRATEGY"
)

if [[ -n "$ACTION_JSON" ]]; then
  cmd+=(--action-json "$ACTION_JSON")
else
  cmd+=(--goal "$GOAL")
fi
if [[ -n "$MODEL" ]]; then
  cmd+=(--model "$MODEL")
fi
if [[ -n "$CANDIDATES" ]]; then
  cmd+=(--candidates "$CANDIDATES")
fi
if [[ -n "$FALLBACKS" ]]; then
  cmd+=(--fallbacks "$FALLBACKS")
fi
if [[ -n "$SCREENSHOT_PATH" ]]; then
  cmd+=(--screenshot-path "$SCREENSHOT_PATH")
fi
if [[ "$EXECUTE_FLAG" == "1" ]]; then
  cmd+=(--execute)
fi
if [[ "$ALLOW_DANGEROUS_FLAG" == "1" ]]; then
  cmd+=(--allow-dangerous)
fi

"${cmd[@]}"
