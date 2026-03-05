#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="$(cd "$ROOT_DIR/.." && pwd)"
NOVAADAPT_DIR="$ROOT_DIR"
NOVAPRIME_DIR="$WORKSPACE_DIR/NovaPrime"

RUN_FULL=0
CHECK_GH=1

usage() {
  cat <<'USAGE'
Usage: scripts/codex_resume.sh [--full-tests] [--no-gh] [--help]

Quickly validates handoff state for next Codex session.

Options:
  --full-tests  Run full NovaAdapt test suite (slow)
  --no-gh       Skip GitHub run status lookup
  --help        Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full-tests)
      RUN_FULL=1
      shift
      ;;
    --no-gh)
      CHECK_GH=0
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

section() {
  printf '\n== %s ==\n' "$1"
}

section "Environment"
printf 'Workspace: %s\n' "$WORKSPACE_DIR"
printf 'NovaAdapt: %s\n' "$NOVAADAPT_DIR"
printf 'NovaPrime: %s\n' "$NOVAPRIME_DIR"
printf 'Timestamp: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"

section "NovaAdapt Git State"
git -C "$NOVAADAPT_DIR" status --short --branch
printf '\nRecent commits:\n'
git -C "$NOVAADAPT_DIR" log --oneline -6

section "NovaPrime Git State (informational)"
if [[ -d "$NOVAPRIME_DIR/.git" ]]; then
  git -C "$NOVAPRIME_DIR" status --short --branch || true
  printf '\nRecent commits:\n'
  git -C "$NOVAPRIME_DIR" log --oneline -6 || true
  printf '\nNOTE: Do not reset/revert unrelated dirty files in NovaPrime without explicit user direction.\n'
else
  printf 'NovaPrime repo not found at %s\n' "$NOVAPRIME_DIR"
fi

section "Roadmap Pointer"
printf 'Read: %s\n' "$NOVAADAPT_DIR/MASTER_HANDOFF_ROADMAP.md"

section "Targeted NovaAdapt Checks"
(
  cd "$NOVAADAPT_DIR"
  PYTHONPATH=core:shared python3 -m unittest tests.test_server
)

if [[ "$RUN_FULL" -eq 1 ]]; then
  section "Full NovaAdapt Test Suite"
  (
    cd "$NOVAADAPT_DIR"
    PYTHONPATH=core:shared python3 -m unittest discover -s tests
  )
else
  section "Full Suite Skipped"
  printf 'Pass --full-tests to run: PYTHONPATH=core:shared python3 -m unittest discover -s tests\n'
fi

if [[ "$CHECK_GH" -eq 1 ]]; then
  section "Latest GitHub Runs (main)"
  if command -v gh >/dev/null 2>&1; then
    (
      cd "$NOVAADAPT_DIR"
      gh run list --branch main --limit 5 || true
    )
  else
    printf 'gh CLI not installed; skipping run lookup\n'
  fi
fi

section "Resume Summary"
printf '1) Continue from NovaAdapt main and roadmap P1 next item.\n'
printf '2) Preserve standalone-first invariants and optional NovaPrime integration.\n'
printf '3) Entropy remains lore-only; do not map as real-world control logic.\n'
printf '4) Keep changes minimal and covered by tests before pushing.\n'

printf '\nResume checklist complete.\n'
