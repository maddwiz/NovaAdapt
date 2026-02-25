# vibe

Wearable bridge prototype for on-the-go command capture.

## What Exists

- `vibe_terminal.py`: terminal-driven "voice intent" sender.
  - Sends objectives to bridge/core via `run_async`.
  - Optional polling mode to wait for terminal job state.
  - Designed as a drop-in stand-in for glasses speech-to-text events.

## Quick Use

From repo root:

```bash
PYTHONPATH=core:shared python3 vibe/vibe_terminal.py \
  --bridge-url http://127.0.0.1:9797 \
  --token YOUR_BRIDGE_TOKEN \
  --objective "Build a dark mode dashboard and run tests" \
  --wait
```

Interactive mode:

```bash
PYTHONPATH=core:shared python3 vibe/vibe_terminal.py \
  --bridge-url http://127.0.0.1:9797 \
  --token YOUR_BRIDGE_TOKEN
```

Type objectives line-by-line. Type `quit` to exit.
