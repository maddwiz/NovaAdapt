# core

Desktop orchestration runtime.

Contains:

- CLI (`novaadapt`) entrypoint.
- Model-plan-to-action agent loop.
- Action safety policy and execution gating.
- DirectShell adapter for preview and execution (`subprocess`, `http`, `daemon`).
- DirectShell readiness probe command (`novaadapt directshell-check`).
- History/undo command support via shared SQLite queue.
- Audit log query command support (`novaadapt events`).
- Audit event watch support (`novaadapt events-watch`).
- SQLite snapshot command support (`novaadapt backup`).
- SQLite restore command support (`novaadapt restore`).
- SQLite housekeeping command support (`novaadapt prune`).
- Service layer reusable by CLI and HTTP API server.
- Async job manager for long-running API requests.
- SSE job stream endpoint for live status (`GET /jobs/{id}/stream`).
- SSE plan stream endpoint for live status (`GET /plans/{id}/stream`).
- SSE audit stream endpoint for live events (`GET /events/stream`).
- Persisted approval-plan workflow (`/plans`, `approve`, `reject`).
- Persisted audit event log (`GET /events`).
- Optional bearer auth guard on API routes.
- Optional request rate limiting and max body-size enforcement.
- Optional idempotency key store for mutating POST routes.
- Optional audit retention cleanup for persisted event logs.
- Hot-path SQLite indexes for list/filter/prune operations at scale.
- Versioned SQLite schema migrations for deterministic DB upgrades.
- Core metrics endpoint (`/metrics`) for API counters.
- Optional OpenTelemetry trace export for request spans.
- Dashboard JSON endpoint (`/dashboard/data`) for live UI polling.
