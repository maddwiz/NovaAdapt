#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${NOVAADAPT_CONFIG_PATH:-$ROOT_DIR/config/models.example.json}"
GOAL="${NOVAADAPT_VISION_GOAL:-Click the visible continue button}"
MODEL="${NOVAADAPT_VISION_MODEL:-}"
STRATEGY="${NOVAADAPT_VISION_STRATEGY:-single}"
CANDIDATES="${NOVAADAPT_VISION_CANDIDATES:-}"
FALLBACKS="${NOVAADAPT_VISION_FALLBACKS:-}"
APP_NAME="${NOVAADAPT_VISION_APP_NAME:-}"
SCREENSHOT_PATH="${1:-${NOVAADAPT_SCREENSHOT_PATH:-}}"
EXECUTE_FLAG="${NOVAADAPT_DEMO_EXECUTE:-0}"
ALLOW_DANGEROUS_FLAG="${NOVAADAPT_ALLOW_DANGEROUS:-0}"

if [[ -z "$SCREENSHOT_PATH" ]]; then
  echo "usage: $(basename "$0") /absolute/path/to/screenshot.png" >&2
  echo "or set NOVAADAPT_SCREENSHOT_PATH." >&2
  exit 1
fi

if [[ ! -f "$SCREENSHOT_PATH" ]]; then
  echo "screenshot not found: $SCREENSHOT_PATH" >&2
  exit 1
fi

PYTHONPATH="$ROOT_DIR/core:$ROOT_DIR/shared${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

cmd=(
  python3 -m novaadapt_core.cli vision-execute
  --config "$CONFIG_PATH"
  --goal "$GOAL"
  --strategy "$STRATEGY"
  --screenshot-path "$SCREENSHOT_PATH"
)

if [[ -n "$MODEL" ]]; then
  cmd+=(--model "$MODEL")
fi
if [[ -n "$CANDIDATES" ]]; then
  cmd+=(--candidates "$CANDIDATES")
fi
if [[ -n "$FALLBACKS" ]]; then
  cmd+=(--fallbacks "$FALLBACKS")
fi
if [[ -n "$APP_NAME" ]]; then
  cmd+=(--app-name "$APP_NAME")
fi
if [[ "$EXECUTE_FLAG" == "1" ]]; then
  cmd+=(--execute)
fi
if [[ "$ALLOW_DANGEROUS_FLAG" == "1" ]]; then
  cmd+=(--allow-dangerous)
fi

"${cmd[@]}"
