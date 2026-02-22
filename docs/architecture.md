# NovaAdapt Architecture (Desktop MVP)

## Control Loop

1. User sends objective to `novaadapt run`.
2. `ModelRouter` selects one model (`single`) with optional fallback chain, or collects multiple responses (`vote`).
3. `NovaAdaptAgent` parses strict JSON action plans.
4. `ActionPolicy` evaluates each action for risk before execution.
5. `DirectShellClient` previews or executes each action (subprocess or HTTP transport).
6. `UndoQueue` stores every action, optional undo action, and status in local SQLite.
7. Optional async runner (`/run_async`) executes long tasks through in-memory job manager.

## API Surface

`novaadapt serve` exposes the same operations over HTTP:

- `POST /run` for objective execution.
- `POST /run_async` for queued objective execution.
- `GET /jobs` and `GET /jobs/{id}` for job polling.
- `POST /undo` for action reversal.
- `GET /models` and `POST /check` for model routing visibility.
- `GET /history` for audit state.

Bearer token auth can be required for all routes except `/health`.
All responses include `X-Request-ID` for request-level tracing across bridge/core.

## Relay Layer

`novaadapt-bridge` is a Go secure relay process for remote devices. It enforces a bridge ingress token and forwards to the core API using a separate upstream token.

It also preserves per-request tracing through `X-Request-ID` and supports deep upstream health checks for relay monitoring.
The bridge additionally exposes `/metrics` for request and error counters.

## Delivery Tooling

- Cross-language CI runs Python unit tests and Go bridge tests on every push/PR.
- A local smoke script (`scripts/smoke_bridge.sh`) validates auth and tracing across core + bridge.

## Reliability Track

- Multi-model voting provides consensus-based planning.
- Dry-run default prevents unintended UI operations.
- Destructive actions require explicit override (`--allow-dangerous`).
- Single strategy can automatically fail over to configured fallback models.
- Action log is an auditable queue for replay/undo workflows.

## Next Integration Points

- Replace subprocess DirectShell call with daemon/gRPC API once available.
- Add bridge auth channel and device trust registry.
- Add Tauri desktop approval panel for action preview and one-tap undo.
