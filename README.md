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
  - Deterministic vote winner selection with optional quorum (`min_vote_agreement`).
  - Health probes and resilient fallback for single-model mode.
  - API client SDK for core/bridge (`NovaAdaptAPIClient`).
- `core` Python CLI orchestrator that:
  - Requests an action plan from selected model(s).
  - Supports explicit plan approval workflow (`create -> approve/reject`).
  - Parses JSON actions.
  - Enforces execution guardrails for destructive actions.
  - Sends actions to DirectShell (or dry-run preview).
  - Records each action in a local undo queue database.
  - Exposes HTTP API with optional bearer auth and async jobs.
- `bridge` relay service in Go for secure remote forwarding into core API.

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

`--candidates` is optional in vote mode; if omitted, NovaAdapt uses configured defaults (`routing.default_vote_candidates`).
No GUI actions are executed unless `--execute` is provided.

5. Review action history and preview/execute undo:

```bash
novaadapt history --limit 10
novaadapt undo --id 12
novaadapt undo --id 12 --execute
```

Inspect persisted audit events:

```bash
novaadapt events --limit 20
novaadapt events --category plans --entity-type plan
novaadapt events-watch --since-id 120 --timeout-seconds 10
```

6. Create and manage approval plans:

```bash
novaadapt plan-create --objective "Open browser and go to example.com"
novaadapt plans --limit 10
novaadapt plan-approve --id PLAN_ID         # executes by default
novaadapt plan-reject --id PLAN_ID --reason "Not safe enough"
```

7. Probe model health:

```bash
novaadapt check --config config/models.local.json
novaadapt check --config config/models.local.json --models local-qwen,openai-gpt
```

8. Start local HTTP API (for phone/glasses/bridge clients):

```bash
novaadapt serve \
  --config config/models.local.json \
  --host 127.0.0.1 \
  --port 8787 \
  --jobs-db-path ~/.novaadapt/jobs.db \
  --audit-db-path ~/.novaadapt/events.db \
  --api-token YOUR_CORE_TOKEN \
  --log-requests \
  --rate-limit-rps 20 \
  --rate-limit-burst 20 \
  --max-body-bytes 1048576
```

API endpoints:

- `GET /health`
- `GET /openapi.json`
- `GET /dashboard` (auth-protected operational HTML dashboard)
- `GET /dashboard/data` (auth-protected dashboard JSON: health, metrics, jobs, plans, events)
- `GET /models`
- `GET /history?limit=20`
- `GET /metrics` (Prometheus-style counters, auth-protected when token is enabled)
- `GET /events?limit=100` (audit log filters: `category`, `entity_type`, `entity_id`, `since_id`)
- `GET /events/stream` (SSE audit stream, supports `timeout`, `interval`, `since_id`)
- `POST /run` with JSON payload
- `POST /run_async` with JSON payload (returns `job_id`)
- `GET /jobs` and `GET /jobs/{id}`
- `GET /jobs/{id}/stream` (SSE status updates)
- `POST /jobs/{id}/cancel`
- `GET /plans` and `GET /plans/{id}`
- `GET /plans/{id}/stream` (SSE status updates)
- `POST /plans` (create pending plan)
- `POST /plans/{id}/approve` (execute on approval by default)
- `POST /plans/{id}/approve_async` (queue approval/execution as async job)
- `POST /plans/{id}/reject`
- `POST /plans/{id}/undo` (reverse undo of recorded plan actions)
- `POST /undo` with JSON payload
- `POST /check` with JSON payload

Core API responses include `X-Request-ID` for tracing (and object responses also include `request_id` in JSON).
Mutating POST routes support idempotency via `Idempotency-Key`; replayed responses return `X-Idempotency-Replayed: true`.
Audit events are persisted in SQLite (`--audit-db-path`) and include request IDs for forensic tracing.
Plan records expose execution progress fields (`progress_completed`, `progress_total`) and terminal error state (`execution_error`).
Plans finalize as `failed` when one or more actions are blocked or fail during execution.

When token auth is enabled, browser dashboard usage supports:

```text
/dashboard?token=YOUR_CORE_TOKEN
```

The page will reuse that token for `/dashboard/data` polling.

9. Run full local smoke test (core + bridge):

```bash
make smoke
```

## Dev Commands

```bash
make test      # Python + Go tests
make test-py   # Python tests only
make test-go   # Go bridge tests only
make build-bridge
```

## Benchmarking

```bash
PYTHONPATH=core:shared python3 -m novaadapt_core.cli benchmark \
  --config config/models.example.json \
  --suite config/benchmark.example.json \
  --out results/benchmark.json
```

This produces pass/fail and success-rate metrics so reliability progress can be tracked objectively.

## MCP Server

```bash
PYTHONPATH=core:shared python3 -m novaadapt_core.cli mcp \
  --config config/models.example.json
```

Exposed tools:
- `novaadapt_run`
- `novaadapt_models`
- `novaadapt_check`
- `novaadapt_history`
- `novaadapt_events`
- `novaadapt_events_wait`
- `novaadapt_plan_create`
- `novaadapt_plans`
- `novaadapt_plan_get`
- `novaadapt_plan_approve`
- `novaadapt_plan_reject`
- `novaadapt_plan_undo`

## Docker Deployment

```bash
./installer/gen_dev_tokens.sh   # optional: writes deploy/.env
./installer/run_docker_stack.sh
```

Compose stack file:

- `/Users/desmondpottle/Documents/New project/NovaAdapt/deploy/docker-compose.yml`

## Python API Client

```python
from novaadapt_shared import NovaAdaptAPIClient

client = NovaAdaptAPIClient(base_url="http://127.0.0.1:8787", token="YOUR_CORE_TOKEN")
print(client.models())
print(client.run("Open browser and go to example.com"))
print(client.job_stream("job-id", timeout_seconds=10))
print(client.plan_stream("plan-id", timeout_seconds=10))
print(client.events(limit=20))
```

`NovaAdaptAPIClient` retries transient HTTP failures by default (`max_retries=1`), configurable per client instance.

8. Build and start secure bridge relay:

```bash
./installer/build_bridge_go.sh
./bridge/bin/novaadapt-bridge \
  --host 127.0.0.1 \
  --port 9797 \
  --core-url http://127.0.0.1:8787 \
  --bridge-token YOUR_BRIDGE_TOKEN \
  --core-token YOUR_CORE_TOKEN \
  --log-requests true
```

Bridge realtime control endpoint:

- `GET /ws` (WebSocket; streams audit events and accepts authenticated command/approval requests)

## Model-Agnostic Design

`shared/novaadapt_shared/model_router.py` treats providers as endpoint definitions, not hardcoded vendors. Any model that supports OpenAI-style chat completions can be used by setting:

- `base_url`
- `model`
- `api_key_env` (if required)

This includes local Ollama (`http://localhost:11434/v1`), self-hosted vLLM, or managed endpoints.

Vote mode reliability controls (in model config):

```json
"routing": {
  "default_vote_candidates": 3,
  "min_vote_agreement": 1
}
```

Set `min_vote_agreement` to `2` or `3` when you want stricter consensus before actions execute.

Single mode also supports fallback chain routing:

```bash
novaadapt run \
  --config config/models.local.json \
  --objective "Open Slack and search for release notes" \
  --strategy single \
  --model local-qwen \
  --fallbacks openai-gpt,custom-vllm
```

## DirectShell Transport Modes

- `subprocess` (default): runs `directshell exec --json ...` using `DIRECTSHELL_BIN`.
- `http`: sends `POST` to `DIRECTSHELL_HTTP_URL` with body `{"action": ...}`.

Environment variables:

- `DIRECTSHELL_TRANSPORT` = `subprocess` or `http`
- `DIRECTSHELL_BIN` (subprocess mode)
- `DIRECTSHELL_HTTP_URL` (http mode, default `http://127.0.0.1:8765/execute`)

## Security Baseline

- Dry-run by default.
- Action execution is explicit (`--execute`).
- Potentially destructive actions are blocked unless `--allow-dangerous` is set.
- Plans are capped by `--max-actions` (default `25`) to reduce runaway execution.
- Every action is logged in SQLite (`~/.novaadapt/actions.db`) for audit/undo workflows.
- Core API can require bearer auth via `--api-token` / `NOVAADAPT_API_TOKEN`.
- Bridge relay enforces independent ingress token and forwards with a separate core token.
- Bridge relay propagates `X-Request-ID` for traceability and supports deep health probing at `/health?deep=1`.
- Bridge relay exposes `/metrics` for basic operational counters.
- Bridge relay forwards `/openapi.json` so remote clients can discover contract shape.
- Bridge relay forwards `/dashboard` HTML for secure remote browser access.
- Core API supports configurable request rate limiting and max body size on `serve`.
- Core API supports persisted idempotency keys on `serve` (`--idempotency-db-path`) to prevent duplicate mutations on retries.
- Async job records can be persisted to SQLite (`--jobs-db-path`) for restart-safe history.
- Plan approval records can be persisted to SQLite (`--plans-db-path`) for restart-safe approvals/audits.

## License

MIT (inherit/update as needed for full product release).
