# NovaAdapt Architecture (Desktop MVP)

## Control Loop

1. User sends objective to `novaadapt run`.
2. `ModelRouter` selects one model (`single`) or collects multiple responses (`vote`).
3. `NovaAdaptAgent` parses strict JSON action plans.
4. `DirectShellClient` previews or executes each action.
5. `UndoQueue` stores every action and status in local SQLite.

## Reliability Track

- Multi-model voting provides consensus-based planning.
- Dry-run default prevents unintended UI operations.
- Action log is an auditable queue for replay/undo workflows.

## Next Integration Points

- Replace subprocess DirectShell call with daemon/gRPC API once available.
- Add bridge auth channel and device trust registry.
- Add Tauri desktop approval panel for action preview and one-tap undo.
