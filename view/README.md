# view

Realtime companion console for NovaAdapt bridge WebSocket control and remote terminal access.

## What Exists

- `realtime_console.html`: single-file mobile-friendly UI.
  - Connects to bridge `/ws`.
  - Issues scoped session tokens via `/auth/session`.
  - Generates Android pairing payloads via `/auth/pair`.
  - Revokes scoped sessions via `/auth/session/revoke` (token or `session_id`).
  - Lists/adds/removes bridge trusted device IDs via `/auth/devices` and `/auth/devices/remove`.
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

Bootstrap query params supported by `realtime_console.html`:

- `ws_url`
- `bridge_http_url`
- `token`
- `admin_token`
- `device_id`
- `auto_connect=1`

The console now persists non-sensitive connection defaults locally in browser storage:

- websocket URL
- bridge HTTP URL
- device ID
- session scope / TTL defaults
- cursor + poll settings
- allowlist device ID

If using query auth mode:

- token: scoped bridge session token (or static bridge token)
- admin token: bridge admin token (or admin-scoped session token) for issue/revoke operations
- device id: trusted `X-Device-ID` value when device allowlist is enabled

## Plug-and-Play Android Pairing

`realtime_console.html` now includes a `Mobile Pairing` card that generates:

- a long-lived operator session token
- an optional admin session token
- a raw pairing code
- a `novaadapt://pair?payload=...` deep link
- a QR code for scanning the deep link from Android

Recommended flow for non-technical users:

1. Open the realtime console on the desktop machine that already has bridge admin access.
2. Fill the `Mobile Pairing` card and click `Generate Pairing`.
3. Open the generated deep link on Android or copy the pairing code into the native operator app.
4. If the user is on the same LAN but not yet paired, the Android shell can use `Discover Nearby` to locate the bridge and prefill the host automatically.
5. The Android shell imports the manifest, stores the connection settings, and opens the operator console automatically.

## Notes

- This is intentionally static and dependency-light for quick operator workflows (xterm.js is loaded from CDN).
- Production iPhone/native module can reuse the same WebSocket message contract.
