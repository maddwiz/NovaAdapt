#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_PRIMARY="$ROOT_DIR/results/benchmark.novaadapt.json"
FALLBACK_PRIMARY="$ROOT_DIR/results/benchmark.json"
if [[ -f "$DEFAULT_PRIMARY" ]]; then
  PRIMARY_PATH="$DEFAULT_PRIMARY"
else
  PRIMARY_PATH="$FALLBACK_PRIMARY"
fi
PRIMARY_PATH="${1:-${NOVAADAPT_BENCH_PRIMARY:-$PRIMARY_PATH}}"
OUT_DIR="${NOVAADAPT_BENCH_OUT_DIR:-$ROOT_DIR/results/publication}"
TITLE="${NOVAADAPT_BENCH_TITLE:-NovaAdapt Reliability Benchmark}"
PRIMARY_NAME="${NOVAADAPT_PRIMARY_NAME:-NovaAdapt}"
NOTES="${NOVAADAPT_BENCH_NOTES:-Generated from locally available benchmark reports.}"

if [[ ! -f "$PRIMARY_PATH" ]]; then
  echo "primary benchmark report not found: $PRIMARY_PATH" >&2
  exit 1
fi

baseline_args=()
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  [[ "$path" == "$PRIMARY_PATH" ]] && continue
  base="$(basename "$path")"
  case "$base" in
    benchmark.compare.json|benchmark.compare.md|benchmark.json)
      continue
      ;;
  esac
  stem="${base#benchmark.}"
  stem="${stem%.json}"
  [[ -z "$stem" ]] && continue
  label="$(printf '%s' "$stem" | awk -F '[-_.]' '{for (i = 1; i <= NF; i++) printf toupper(substr($i,1,1)) substr($i,2)}')"
  baseline_args+=(--baseline "$label=$path")
done < <(find "$ROOT_DIR/results" -maxdepth 1 -type f -name 'benchmark*.json' | sort)

PYTHONPATH="$ROOT_DIR/core:$ROOT_DIR/shared${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH

cmd=(
  python3 -m novaadapt_core.cli benchmark-publish
  --primary "$PRIMARY_PATH"
  --primary-name "$PRIMARY_NAME"
  --out-dir "$OUT_DIR"
  --md-title "$TITLE"
  --notes "$NOTES"
)
if (( ${#baseline_args[@]} )); then
  cmd+=("${baseline_args[@]}")
fi
"${cmd[@]}"
