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
- Optional bearer auth guard on API routes.
