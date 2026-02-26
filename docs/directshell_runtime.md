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
- `right_click` (coordinates)
- `double_click` (coordinates)
- `wait`
- `run_shell`
- `note`

`open_app` accepts app arguments on all platforms.
For app names containing spaces, quote the app name in the action value/target (example: `"Google Chrome" --incognito`).

Linux note:
- `type`, `key`, `hotkey`, and `click` use `xdotool`; install it for full Linux desktop action support.

Windows note:
- `type`, `key`, `hotkey`, and `click` use PowerShell (`powershell` or `pwsh`) with `System.Windows.Forms.SendKeys`.

## Browser Runtime (Playwright)

NovaAdapt also supports a Playwright-backed browser execution runtime for web apps.

Supported browser action types:

- `navigate`
- `click_selector`
- `fill`
- `extract_text`
- `screenshot`
- `wait_for_selector`
- `evaluate_js`
- `new_context` (reset browser context/session state)
- `new_page`
- `list_pages`
- `switch_page` (`page_id` or `index`)
- `close_page` (`page_id` or `index`, defaults to current)

Install browser support:

```bash
pip install -e '.[browser]'
python -m playwright install chromium
```

Optional browser safety env vars:

- `NOVAADAPT_BROWSER_ALLOWLIST` (comma-separated domains)
- `NOVAADAPT_BROWSER_BLOCKLIST` (comma-separated domains)
- `NOVAADAPT_BROWSER_ALLOW_SENSITIVE_FILL` (`true` to allow password/token autofill)
- `NOVAADAPT_BROWSER_SCREENSHOT_DIR` (default `~/.novaadapt/browser_screenshots`)
- `NOVAADAPT_BROWSER_HEADLESS` (`true` by default)

## Optional External Transports

- `native` (default): built-in NovaAdapt runtime
- `subprocess`: invokes `directshell exec --json ...`
- `http`: posts JSON action payloads to a DirectShell HTTP endpoint
- `daemon`: framed JSON over Unix socket or TCP
- `browser`: built-in Playwright browser runtime

`daemon` can point to:

- external DirectShell daemon endpoint
- built-in NovaAdapt daemon (`novaadapt native-daemon`)

`http` can point to:

- external DirectShell HTTP endpoint
- built-in NovaAdapt HTTP endpoint (`novaadapt native-http`)

Optional transport auth:

- `DIRECTSHELL_HTTP_TOKEN`: sent as `X-DirectShell-Token` for HTTP transport and probe.
- `DIRECTSHELL_DAEMON_TOKEN`: included in daemon payloads and enforceable by `novaadapt native-daemon`.

## Runtime Readiness Probe

Use the built-in check before enabling live execution:

```bash
novaadapt directshell-check
novaadapt directshell-check --transport browser
```

Outputs include `ok`, selected transport, and transport-specific diagnostics.

When using native mode with optional fallback transport:

```bash
export DIRECTSHELL_TRANSPORT=native
export DIRECTSHELL_NATIVE_FALLBACK_TRANSPORT=http
export DIRECTSHELL_HTTP_URL=http://127.0.0.1:8765/execute
export DIRECTSHELL_HTTP_TOKEN=YOUR_DS_TOKEN
novaadapt directshell-check --transport native --native-fallback-transport http --http-token YOUR_DS_TOKEN
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
novaadapt native-daemon --socket '' --host 127.0.0.1 --port 8766 --daemon-token YOUR_DS_TOKEN
```

Then configure core execution transport:

```bash
export DIRECTSHELL_TRANSPORT=daemon
export DIRECTSHELL_DAEMON_SOCKET=/tmp/directshell.sock
```

## Built-In HTTP Endpoint

Expose native runtime over HTTP:

```bash
novaadapt native-http --host 127.0.0.1 --port 8765
```

With optional token:

```bash
novaadapt native-http --host 127.0.0.1 --port 8765 --http-token YOUR_DS_TOKEN
```

Then configure core execution transport:

```bash
export DIRECTSHELL_TRANSPORT=http
export DIRECTSHELL_HTTP_URL=http://127.0.0.1:8765/execute
export DIRECTSHELL_HTTP_TOKEN=YOUR_DS_TOKEN
```

For remote monitoring via core API:

```text
GET /health?deep=1&execution=1
```

This returns `503` when the configured execution backend is not ready.

## Planned

- First-party gRPC execution backend for richer deterministic UI control.
