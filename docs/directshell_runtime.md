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

`daemon` can point to:

- external DirectShell daemon endpoint
- built-in NovaAdapt daemon (`novaadapt native-daemon`)

## Runtime Readiness Probe

Use the built-in check before enabling live execution:

```bash
novaadapt directshell-check
```

Outputs include `ok`, selected transport, and transport-specific diagnostics.

When using native mode with optional fallback transport:

```bash
export DIRECTSHELL_TRANSPORT=native
export DIRECTSHELL_NATIVE_FALLBACK_TRANSPORT=http
export DIRECTSHELL_HTTP_URL=http://127.0.0.1:8765/execute
novaadapt directshell-check --transport native --native-fallback-transport http
```

Fallback transport executes only when native action execution returns a non-`ok` status.

## Built-In Daemon Endpoint

Expose native runtime over DirectShell-compatible framed JSON:

```bash
novaadapt native-daemon --socket /tmp/directshell.sock
```

Or TCP mode:

```bash
novaadapt native-daemon --socket '' --host 127.0.0.1 --port 8766
```

Then configure core execution transport:

```bash
export DIRECTSHELL_TRANSPORT=daemon
export DIRECTSHELL_DAEMON_SOCKET=/tmp/directshell.sock
```

For remote monitoring via core API:

```text
GET /health?deep=1&execution=1
```

This returns `503` when the configured execution backend is not ready.

## Planned

- First-party gRPC execution backend for richer deterministic UI control.
