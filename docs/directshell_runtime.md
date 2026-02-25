# DirectShell Runtime Contract

NovaAdapt includes a built-in native desktop execution runtime.
External DirectShell endpoints are still supported as optional transports.

## Built-In Runtime (Default)

Supported action types:

- `open_app`
- `open_url`
- `type`
- `key`
- `hotkey`
- `click` (coordinates)
- `wait`
- `run_shell`
- `note`

## Optional External Transports

- `native` (default): built-in NovaAdapt runtime
- `subprocess`: invokes `directshell exec --json ...`
- `http`: posts JSON action payloads to a DirectShell HTTP endpoint
- `daemon`: framed JSON over Unix socket or TCP

## Runtime Readiness Probe

Use the built-in check before enabling live execution:

```bash
novaadapt directshell-check
```

Outputs include `ok`, selected transport, and transport-specific diagnostics.

For remote monitoring via core API:

```text
GET /health?deep=1&execution=1
```

This returns `503` when the configured execution backend is not ready.

## Planned

- First-party gRPC execution backend for richer deterministic UI control.
