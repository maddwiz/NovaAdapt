# view

Realtime companion console for NovaAdapt bridge WebSocket control.

## What Exists

- `realtime_console.html`: single-file mobile-friendly UI.
  - Connects to bridge `/ws`.
  - Streams live audit events.
  - Sends authenticated command requests (run/plan approve/job cancel/etc.).
  - Shows command responses and errors in a timestamped event log.

## Run Locally

From repo root:

```bash
cd view
python3 -m http.server 8088
```

Then open:

- `http://127.0.0.1:8088/realtime_console.html`

Recommended bridge URL in the UI:

- `ws://127.0.0.1:9797/ws`

If using query auth mode:

- token: bridge token
- device id: trusted `X-Device-ID` value when device allowlist is enabled

## Notes

- This is intentionally static and dependency-free for quick operator workflows.
- Production iPhone/native module can reuse the same WebSocket message contract.
