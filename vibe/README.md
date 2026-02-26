# vibe

Wearable bridge prototype for on-the-go command capture.

## What Exists

- `vibe_terminal.py`: terminal-driven "voice intent" sender.
  - Sends objectives to bridge/core via `run_async`.
  - Can mint short-lived scoped session tokens from an admin token.
  - Can pre-allowlist its device ID before session minting (`--ensure-device-allowlisted`).
  - Revokes leased session token on exit by default.
  - Optional polling mode to wait for terminal job state.
  - Designed as a drop-in stand-in for glasses speech-to-text events.

## Quick Use

From repo root:

```bash
PYTHONPATH=core:shared python3 vibe/vibe_terminal.py \
  --bridge-url http://127.0.0.1:9797 \
  --admin-token YOUR_BRIDGE_ADMIN_TOKEN \
  --ensure-device-allowlisted \
  --session-device-id iphone-15-pro \
  --session-scopes read,run,plan,approve,reject,undo,cancel \
  --objective "Build a dark mode dashboard and run tests" \
  --wait
```

Interactive mode:

```bash
PYTHONPATH=core:shared python3 vibe/vibe_terminal.py \
  --bridge-url http://127.0.0.1:9797 \
  --admin-token YOUR_BRIDGE_ADMIN_TOKEN
```

Type objectives line-by-line. Type `quit` to exit.

If needed, direct token mode is still available:

```bash
PYTHONPATH=core:shared python3 vibe/vibe_terminal.py \
  --bridge-url http://127.0.0.1:9797 \
  --token YOUR_BRIDGE_TOKEN
```
