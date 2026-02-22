# NovaAdapt Architecture (Desktop MVP)

## Control Loop

1. User sends objective to `novaadapt run`.
2. `ModelRouter` selects one model (`single`) with optional fallback chain, or collects multiple responses (`vote`).
3. `NovaAdaptAgent` parses strict JSON action plans.
4. `ActionPolicy` evaluates each action for risk before execution.
5. `DirectShellClient` previews or executes each action (subprocess or HTTP transport).
6. `UndoQueue` stores every action, optional undo action, and status in local SQLite.

## API Surface

`novaadapt serve` exposes the same operations over HTTP:

- `POST /run` for objective execution.
- `POST /undo` for action reversal.
- `GET /models` and `POST /check` for model routing visibility.
- `GET /history` for audit state.

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
