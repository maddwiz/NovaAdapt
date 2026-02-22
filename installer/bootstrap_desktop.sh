#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .

if [[ ! -f config/models.local.json ]]; then
  cp config/models.example.json config/models.local.json
fi

echo "NovaAdapt desktop MVP bootstrapped."
echo "Next: source .venv/bin/activate && novaadapt models --config config/models.local.json"
