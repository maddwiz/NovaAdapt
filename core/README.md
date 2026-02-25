# core

Desktop orchestration runtime.

Contains:

- CLI (`novaadapt`) entrypoint.
- Model-plan-to-action agent loop.
- Action safety policy and execution gating.
- DirectShell adapter for preview and execution.
- History/undo command support via shared SQLite queue.
- Service layer reusable by CLI and HTTP API server.
- Async job manager for long-running API requests.
- SSE job stream endpoint for live status (`GET /jobs/{id}/stream`).
- Persisted approval-plan workflow (`/plans`, `approve`, `reject`).
- Optional bearer auth guard on API routes.
- Optional request rate limiting and max body-size enforcement.
- Optional idempotency key store for mutating POST routes.
- Core metrics endpoint (`/metrics`) for API counters.
- Dashboard JSON endpoint (`/dashboard/data`) for live UI polling.
