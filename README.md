# NovaAdapt

Any app. Any model. Anywhere.

NovaAdapt is a universal AI adapter designed to control desktop software through a deterministic execution layer, while staying model-agnostic. The first milestone in this repo is a desktop-first MVP with:

- Model router with local-first defaults and cloud/custom endpoint support.
- Optional multi-model voting for safer action selection.
- DirectShell integration point for deterministic GUI actions.
- Local undo log and action history via SQLite.

## Current Status (Desktop MVP)

Implemented now:

- Monorepo scaffold (`core`, `vibe`, `view`, `bridge`, `shared`, `installer`, `desktop`, `mobile`, `wearables`).
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
  - Includes realtime WebSocket control channel (`/ws`) for events + command relay.
- `view` static realtime console UI for bridge operations (`view/realtime_console.html`).
- `desktop` Tauri shell scaffold for first-party approval UX (`desktop/tauri-shell`) (not production-ready).
- `mobile` iOS SwiftUI companion scaffold (`mobile/ios/NovaAdaptCompanion`) (not production-ready).
- `wearables` Halo/Omi adapter scaffold (`wearables/halo_bridge.py`) (not production-ready).

Planned next:

- Harden first-party desktop/mobile/wearable builds into signed release artifacts.
- Expand the built-in execution runtime with a richer gRPC backend for deterministic control.
- Expand native clients from scaffold to production app-store ready deliverables.

## Monorepo Layout

```text
NovaAdapt/
├── core/          # Desktop orchestrator + DirectShell adapter
├── desktop/       # Tauri desktop shell scaffold
├── vibe/          # Wearable intent bridge prototype (`vibe_terminal.py`)
├── view/          # Realtime operator console + iPhone module seed
├── mobile/        # Native mobile companion scaffolds
├── wearables/     # Wearable device adapter scaffolds
├── bridge/        # Secure relay server (Go, production-ready)
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

8. Snapshot local state databases (recommended before upgrades):

```bash
novaadapt backup --out-dir ~/.novaadapt/backups
```

The command snapshots local SQLite stores (`actions`, `plans`, `jobs`, `idempotency`, `audit`) using timestamped files and reports which ones were missing.

9. Restore local state from a snapshot (archives current DBs before overwrite):

```bash
novaadapt restore --from-dir ~/.novaadapt/backups --timestamp 20260225T120000Z
```

If `--timestamp` is omitted, NovaAdapt restores the latest discovered snapshot in the backup directory.

10. Prune stale local state rows (recommended for long-running installs):

```bash
novaadapt prune \
  --actions-retention-seconds 2592000 \
  --plans-retention-seconds 2592000 \
  --jobs-retention-seconds 2592000 \
  --idempotency-retention-seconds 604800 \
  --audit-retention-seconds 2592000
```

`novaadapt prune` only removes terminal plan/job rows and rows older than the configured retention windows.

11. Start local HTTP API (for phone/glasses/bridge clients):

```bash
novaadapt serve \
  --config config/models.local.json \
  --host 127.0.0.1 \
  --port 8787 \
  --jobs-db-path ~/.novaadapt/jobs.db \
  --audit-db-path ~/.novaadapt/events.db \
  --audit-retention-seconds 2592000 \
  --audit-cleanup-interval-seconds 60 \
  --api-token YOUR_CORE_TOKEN \
  --log-requests \
  --rate-limit-rps 20 \
  --rate-limit-burst 20 \
  --trusted-proxy-cidrs 127.0.0.1/32 \
  --max-body-bytes 1048576
```

API endpoints:

- `GET /health` (liveness)
- `GET /health?deep=1` (readiness snapshot: models + SQLite-backed stores + metrics)
- `GET /health?deep=1&execution=1` (includes DirectShell readiness check; fails if execution backend is not ready)
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
Idempotency records auto-expire (defaults: 7 days retention, 60s cleanup interval) to prevent unbounded DB growth.
Audit events are persisted in SQLite (`--audit-db-path`) and include request IDs for forensic tracing.
Audit events auto-expire by default (30 days retention, 60s cleanup interval) to cap storage growth.
Audit persistence enables WAL mode, busy-timeout handling, and transient SQLite retry for improved resilience under load.
Plan records expose execution progress fields (`progress_completed`, `progress_total`) and terminal error state (`execution_error`).
Plans finalize as `failed` when one or more actions are blocked or fail during execution.

When token auth is enabled, browser dashboard usage supports:

```text
/dashboard?token=YOUR_CORE_TOKEN
```

The page will reuse that token for `/dashboard/data` polling.
Dashboard now includes one-click controls for pending plan approval/rejection, job cancellation, and plan undo marking.

12. Run full local smoke test (core + bridge):

```bash
make smoke
```

## Dev Commands

```bash
make test      # Python + Go tests
make test-py   # Python tests only
make test-go   # Go bridge tests only
make build-bridge
make release-artifacts      # Build dist artifacts (bridge + python + runtime bundle)
make rotate-tokens-dry-run  # Preview token rotation updates
```

## Benchmarking

```bash
PYTHONPATH=core:shared python3 -m novaadapt_core.cli benchmark \
  --config config/models.example.json \
  --suite config/benchmark.example.json \
  --out results/benchmark.json
```

This produces pass/fail and success-rate metrics so reliability progress can be tracked objectively.

## Observability

Install optional tracing deps:

```bash
pip install -e '.[observability]'
```

Start local collector:

```bash
cd deploy
docker compose -f docker-compose.observability.yml up -d
```

Run core with OTLP tracing:

```bash
novaadapt serve \
  --otel-enabled \
  --otel-service-name novaadapt-core \
  --otel-exporter-endpoint http://127.0.0.1:4318/v1/traces
```

Start Prometheus monitoring and alert evaluation for core + bridge:

```bash
cd deploy
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

Prometheus UI is available at `http://127.0.0.1:9090`.

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

## Systemd Deployment (Linux)

Systemd units and env templates are included under:

- `/Users/desmondpottle/Documents/New project/NovaAdapt/deploy/systemd`

Quick install reference:

```bash
sudo ./installer/install_systemd_services.sh
# edit /etc/novaadapt/core.env and /etc/novaadapt/bridge.env
sudo systemctl enable --now novaadapt-core.service
sudo systemctl enable --now novaadapt-bridge.service
```

Rotate long-lived core/bridge tokens:

```bash
./installer/rotate_tokens.sh --dry-run
./installer/rotate_tokens.sh --restart-systemd
```

Build release artifacts (bridge binary, wheel/sdist, runtime bundle, checksums):

```bash
./installer/build_release_artifacts.sh v0.1.0
```

## Python API Client

```python
from novaadapt_shared import NovaAdaptAPIClient

client = NovaAdaptAPIClient(base_url="http://127.0.0.1:8787", token="YOUR_CORE_TOKEN")
print(client.models())
print(client.run("Open browser and go to example.com"))
print(client.job_stream("job-id", timeout_seconds=10))
print(client.plan_stream("plan-id", timeout_seconds=10))
print(client.events(limit=20))
session = client.issue_session_token(scopes=["read", "plan", "approve"], ttl_seconds=900)
print(client.revoke_session_token(session["token"]))
print(client.revoke_session_id(session["session_id"]))
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
  --core-ca-file ./certs/core-ca.pem \
  --core-client-cert-file ./certs/bridge-client.crt \
  --core-client-key-file ./certs/bridge-client.key \
  --tls-cert-file ./certs/bridge.crt \
  --tls-key-file ./certs/bridge.key \
  --trusted-proxy-cidrs 127.0.0.1/32 \
  --allowed-device-ids iphone-15-pro,halo-glasses-1 \
  --log-requests true
```

Bridge realtime control endpoint:

- `GET /ws` (WebSocket; streams audit events and accepts authenticated command/approval requests)
- Browser/native friendly auth query: `/ws?token=...` (and `/ws?...&device_id=...` when device allowlist is enabled)
- `POST /auth/session` (issue scoped, expiring bridge session tokens for least-privilege clients)
- `POST /auth/session/revoke` (admin revocation of scoped bridge session tokens)

Realtime operator console:

```bash
cd view
python3 -m http.server 8088
```

Open `http://127.0.0.1:8088/realtime_console.html`.
The console can mint scoped bridge session tokens via `POST /auth/session`, revoke by token/session ID, and use sessions for websocket control.

One-command local operator stack (core + bridge + optional view server):

```bash
make run-local
```

Optional env vars:
- `NOVAADAPT_CORE_TOKEN`
- `NOVAADAPT_CORE_TRUSTED_PROXY_CIDRS` (trusted proxy CIDRs/IPs for core forwarded client IP handling)
- `NOVAADAPT_ACTION_RETENTION_SECONDS` / `NOVAADAPT_PLANS_RETENTION_SECONDS` / `NOVAADAPT_JOBS_RETENTION_SECONDS`
- `NOVAADAPT_IDEMPOTENCY_RETENTION_SECONDS` / `NOVAADAPT_IDEMPOTENCY_CLEANUP_INTERVAL_SECONDS`
- `NOVAADAPT_AUDIT_RETENTION_SECONDS` / `NOVAADAPT_AUDIT_CLEANUP_INTERVAL_SECONDS`
- `NOVAADAPT_OTEL_ENABLED` / `NOVAADAPT_OTEL_SERVICE_NAME` / `NOVAADAPT_OTEL_EXPORTER_ENDPOINT`
- `NOVAADAPT_BRIDGE_TOKEN`
- `NOVAADAPT_CORE_CA_FILE` (optional CA bundle for bridge->core TLS verification)
- `NOVAADAPT_CORE_CLIENT_CERT_FILE` / `NOVAADAPT_CORE_CLIENT_KEY_FILE` (optional bridge->core mTLS identity)
- `NOVAADAPT_CORE_TLS_SERVER_NAME` (optional SNI/hostname override for bridge->core HTTPS)
- `NOVAADAPT_CORE_TLS_INSECURE_SKIP_VERIFY=1` (dev-only; disables bridge->core cert validation)
- `NOVAADAPT_BRIDGE_ALLOWED_DEVICE_IDS`
- `NOVAADAPT_BRIDGE_CORS_ALLOWED_ORIGINS` (defaults to local view origin when `NOVAADAPT_WITH_VIEW=1`)
- `NOVAADAPT_BRIDGE_TLS_CERT_FILE` / `NOVAADAPT_BRIDGE_TLS_KEY_FILE` (optional HTTPS listener)
- `NOVAADAPT_BRIDGE_TLS_INSECURE_SKIP_VERIFY=1` (local stack health probe skips cert verification when HTTPS uses self-signed certs)
- `NOVAADAPT_BRIDGE_TRUSTED_PROXY_CIDRS` (CIDRs/IPs allowed to set `X-Forwarded-For` / `X-Forwarded-Proto`)
- `NOVAADAPT_BRIDGE_RATE_LIMIT_RPS` (`<=0` disables bridge per-client rate limiting)
- `NOVAADAPT_BRIDGE_RATE_LIMIT_BURST` (bridge per-client burst capacity)
- `NOVAADAPT_BRIDGE_MAX_WS_CONNECTIONS` (max concurrent bridge websocket sessions; `0` disables cap)
- `NOVAADAPT_BRIDGE_REVOCATION_STORE_PATH` (persist bridge session revocations across restart)
- `NOVAADAPT_BRIDGE_ADMIN_TOKEN` (for vibe session leasing)
- `NOVAADAPT_BRIDGE_SESSION_SCOPES` (CSV scopes for leased vibe sessions)
- `NOVAADAPT_BRIDGE_SESSION_TTL` (seconds for leased vibe sessions)
- `NOVAADAPT_WITH_VIEW=0` (skip static view server)

Wearable intent bridge prototype:

```bash
PYTHONPATH=core:shared python3 vibe/vibe_terminal.py \
  --bridge-url http://127.0.0.1:9797 \
  --admin-token YOUR_BRIDGE_ADMIN_TOKEN \
  --objective "Open dashboard and summarize failed jobs" \
  --wait
```

Desktop Tauri shell scaffold:

```bash
cd desktop/tauri-shell
npm install
npm run dev
```

Native iOS scaffold and wearable adapter prototypes:

- `mobile/ios/NovaAdaptCompanion` (SwiftUI source scaffold)
- `wearables/halo_bridge.py` (normalized wearable intent submission helper)
- `docs/realtime_protocol.md` + `config/protocols/realtime.v1.json` (shared realtime contract)

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

- `native` (default): built-in NovaAdapt desktop executor (no external DirectShell binary required).
- `subprocess`: runs `directshell exec --json ...` using `DIRECTSHELL_BIN`.
- `http`: sends `POST` to `DIRECTSHELL_HTTP_URL` with body `{"action": ...}`.
- `http` can target external DirectShell HTTP runtime or NovaAdapt's built-in endpoint (`novaadapt native-http`).
- `daemon`: sends framed JSON RPC over daemon socket/TCP (`DIRECTSHELL_DAEMON_SOCKET` or `DIRECTSHELL_DAEMON_HOST`/`DIRECTSHELL_DAEMON_PORT`). Can target external DirectShell or NovaAdapt's built-in daemon (`novaadapt native-daemon`).

Execution dependency:

- NovaAdapt now includes a built-in native execution runtime for common desktop actions.
- External DirectShell transports (`subprocess`, `http`, `daemon`) are optional for advanced or pre-existing deployments.
- Use `novaadapt directshell-check` to verify the configured transport before running with `--execute`.
- Full runtime contract: `docs/directshell_runtime.md`

Environment variables:

- `DIRECTSHELL_TRANSPORT` = `native`, `subprocess`, `http`, or `daemon`
- `DIRECTSHELL_NATIVE_FALLBACK_TRANSPORT` = `subprocess`, `http`, or `daemon` (optional; only used when primary transport is `native`)
- `DIRECTSHELL_BIN` (subprocess mode)
- `DIRECTSHELL_HTTP_URL` (http mode, default `http://127.0.0.1:8765/execute`)
- `DIRECTSHELL_HTTP_TOKEN` (optional shared token sent as `X-DirectShell-Token` header in http mode)
- `DIRECTSHELL_DAEMON_SOCKET` (daemon Unix socket path, default `/tmp/directshell.sock`; set empty to force TCP)
- `DIRECTSHELL_DAEMON_HOST` / `DIRECTSHELL_DAEMON_PORT` (daemon TCP endpoint, default `127.0.0.1:8766`)
- `DIRECTSHELL_DAEMON_TOKEN` (optional shared token included in daemon payloads and enforceable by `novaadapt native-daemon`)

Readiness probe:

```bash
novaadapt directshell-check
novaadapt directshell-check --transport native --native-fallback-transport http
novaadapt directshell-check --transport http --http-token YOUR_DS_TOKEN
novaadapt directshell-check --transport daemon --daemon-token YOUR_DS_TOKEN
novaadapt directshell-check --transport daemon
```

Run built-in daemon transport endpoint:

```bash
novaadapt native-daemon --socket /tmp/directshell.sock
# or TCP mode
novaadapt native-daemon --socket '' --host 127.0.0.1 --port 8766
# optional daemon auth token
novaadapt native-daemon --socket '' --host 127.0.0.1 --port 8766 --daemon-token YOUR_DS_TOKEN
```

Run built-in HTTP transport endpoint:

```bash
novaadapt native-http --host 127.0.0.1 --port 8765
# optional HTTP auth token
novaadapt native-http --host 127.0.0.1 --port 8765 --http-token YOUR_DS_TOKEN
```

Built-in native action types:

- `open_app`
- `open_url`
- `type`
- `key`
- `hotkey`
- `click` (coordinate target)
- `wait`
- `run_shell`
- `note`

## Security Baseline

- Dry-run by default.
- Action execution is explicit (`--execute`).
- Potentially destructive actions are blocked unless `--allow-dangerous` is set.
- Plans are capped by `--max-actions` (default `25`) to reduce runaway execution.
- Every action is logged in SQLite (`~/.novaadapt/actions.db`) for audit/undo workflows.
- SQLite-backed state stores (plans/jobs/idempotency/audit/action log) run with WAL + busy-timeout defaults and hot-path indexes for safer concurrent access at higher throughput.
- SQLite stores now apply explicit schema migrations recorded in `schema_migrations` for deterministic upgrades across releases.
- Core API can require bearer auth via `--api-token` / `NOVAADAPT_API_TOKEN`.
- Bridge relay enforces independent ingress token and forwards with a separate core token.
- Bridge relay propagates `X-Request-ID` for traceability and supports deep health probing at `/health?deep=1`.
- Bridge relay exposes `/metrics` for basic operational counters.
- Bridge relay can issue short-lived scoped session tokens (`/auth/session`) so view/vibe clients can run with least privilege.
- Bridge relay supports admin session revocation (`/auth/session/revoke`) with denylist enforcement for issued session IDs (optionally persisted via `NOVAADAPT_BRIDGE_REVOCATION_STORE_PATH`).
- Bridge relay forwards `/openapi.json` so remote clients can discover contract shape.
- Bridge relay forwards `/dashboard` HTML for secure remote browser access.
- Bridge relay supports optional per-client request throttling (`NOVAADAPT_BRIDGE_RATE_LIMIT_RPS` / `..._BURST`).
- Bridge relay only trusts forwarded client/protocol headers from configured trusted proxy CIDRs (`NOVAADAPT_BRIDGE_TRUSTED_PROXY_CIDRS`).
- Bridge relay supports bridge->core TLS trust pinning and optional mTLS client identity (`NOVAADAPT_CORE_CA_FILE`, `NOVAADAPT_CORE_CLIENT_CERT_FILE`, `NOVAADAPT_CORE_CLIENT_KEY_FILE`).
- Core API supports per-client request rate limiting and max body size on `serve`.
- Core API only trusts `X-Forwarded-For` for rate-limit identity when `NOVAADAPT_TRUSTED_PROXY_CIDRS` is configured.
- Core API request logging redacts sensitive query params (for example `token`) before writing access logs.
- Core API supports persisted idempotency keys on `serve` (`--idempotency-db-path`) to prevent duplicate mutations on retries.
- Core API supports persisted audit retention controls on `serve` (`--audit-retention-seconds`, `--audit-cleanup-interval-seconds`) to cap event-store growth.
- CLI `novaadapt prune` provides explicit housekeeping for stale rows across actions/plans/jobs/idempotency/audit stores.
- Async job records can be persisted to SQLite (`--jobs-db-path`) for restart-safe history.
- Plan approval records can be persisted to SQLite (`--plans-db-path`) for restart-safe approvals/audits.

## License

Proprietary (All Rights Reserved). See `LICENSE`.
