# NovaAdapt

Any app. Any model. Anywhere.

NovaAdapt is a universal AI adapter designed to control desktop software through a deterministic execution layer, while staying model-agnostic. The first milestone in this repo is a desktop-first MVP with:

- Model router with local-first defaults and cloud/custom endpoint support.
- Optional multi-model voting for safer action selection.
- DirectShell integration point for deterministic GUI actions.
- Local undo log and action history via SQLite.

## Current Status (Desktop MVP)

Implemented now:

- Monorepo scaffold (`core`, `vibe`, `view`, `bridge`, `shared`, `installer`).
- `shared` Python model router with:
  - OpenAI-compatible endpoint support (Ollama, OpenAI, Anthropic-compatible proxies, vLLM, Together, Fireworks, etc.).
  - Optional LiteLLM execution path when `litellm` is installed.
  - Multi-model voting strategy (`single` or `vote`).
- `core` Python CLI orchestrator that:
  - Requests an action plan from selected model(s).
  - Parses JSON actions.
  - Sends actions to DirectShell (or dry-run preview).
  - Records each action in a local undo queue database.

Planned next:

- Tauri desktop UI.
- Real DirectShell daemon connection for richer structured control.
- Relay bridge + glasses + iPhone modules.

## Monorepo Layout

```text
NovaAdapt/
├── core/          # Desktop orchestrator + DirectShell adapter
├── vibe/          # Glasses bridge (placeholder for phase 2)
├── view/          # iPhone companion app (placeholder for phase 3)
├── bridge/        # Secure relay server (placeholder)
├── shared/        # Model router + memory/security primitives
├── installer/     # Desktop setup scripts
├── config/        # Example model and runtime configuration
├── docs/          # Architecture notes
└── tests/         # Unit tests for shared/core logic
```

## Quick Start

1. Create a virtualenv and install editable package:

```bash
cd NovaAdapt
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Copy and customize model config:

```bash
cp config/models.example.json config/models.local.json
```

3. List available configured models:

```bash
novaadapt models --config config/models.local.json
```

4. Run an objective in dry-run mode:

```bash
novaadapt run \
  --config config/models.local.json \
  --objective "Open a browser and navigate to example.com" \
  --strategy vote \
  --candidates local-qwen,openai-gpt
```

No GUI actions are executed unless `--execute` is provided.

## Model-Agnostic Design

`shared/novaadapt_shared/model_router.py` treats providers as endpoint definitions, not hardcoded vendors. Any model that supports OpenAI-style chat completions can be used by setting:

- `base_url`
- `model`
- `api_key_env` (if required)

This includes local Ollama (`http://localhost:11434/v1`), self-hosted vLLM, or managed endpoints.

## Security Baseline

- Dry-run by default.
- Action execution is explicit (`--execute`).
- Every action is logged in SQLite (`~/.novaadapt/actions.db`) for audit/undo workflows.

## License

MIT (inherit/update as needed for full product release).
