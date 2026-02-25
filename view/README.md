# view

Realtime companion console for NovaAdapt bridge WebSocket control and remote terminal access.

## What Exists

- `realtime_console.html`: single-file mobile-friendly UI.
  - Connects to bridge `/ws`.
  - Issues scoped session tokens via `/auth/session`.
  - Revokes scoped sessions via `/auth/session/revoke` (token or `session_id`).
  - Streams live audit events.
  - Sends authenticated command requests (run/plan approve/job cancel/etc.).
  - Starts/attaches remote terminal sessions (`/terminal/sessions*`) with live stdin/stdout over websocket command relay.
  - Shows command responses and errors in a timestamped event log.
- `manifest.webmanifest` + `service-worker.js`: PWA install path for Android.

## Run Locally

From repo root:

```bash
cd view
python3 -m http.server 8088
```

Then open:

- `http://127.0.0.1:8088/realtime_console.html`

Android/PWA install:

- Open `http://127.0.0.1:8088/` from Chrome on Android.
- Use `Add to Home screen` to install the console as a standalone app.

Recommended bridge URL in the UI:

- `ws://127.0.0.1:9797/ws`

If using query auth mode:

- token: scoped bridge session token (or static bridge token)
- admin token: bridge admin token (or admin-scoped session token) for issue/revoke operations
- device id: trusted `X-Device-ID` value when device allowlist is enabled

## Notes

- This is intentionally static and dependency-light for quick operator workflows (xterm.js is loaded from CDN).
- Production iPhone/native module can reuse the same WebSocket message contract.
