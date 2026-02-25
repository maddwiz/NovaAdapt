# DirectShell Runtime Contract

NovaAdapt delegates live desktop action execution to DirectShell.

## What Works Without DirectShell

- Objective planning
- Multi-model routing/voting
- Plan approval/rejection workflows
- Audit, idempotency, undo queue persistence
- Dry-run previews (`--execute` omitted)

## What Requires DirectShell

- Any real GUI action execution (`--execute`)
- Plan approval execution (`/plans/{id}/approve` with `execute=true`)
- Undo execution (`/undo` with `execute=true`)

## Supported Transports

- `subprocess`: invokes `directshell exec --json ...`
- `http`: posts JSON action payloads to a DirectShell HTTP endpoint
- `daemon`: framed JSON over Unix socket or TCP

## Runtime Readiness Probe

Use the built-in check before enabling live execution:

```bash
novaadapt directshell-check
```

Outputs include `ok`, selected transport, and transport-specific diagnostics.

## Planned

- Native gRPC DirectShell client once daemon API contract is finalized.
