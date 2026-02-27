# wearables

Wearable integration adapters for NovaAdapt bridge/core workflows.

All adapters support:

- Intent normalization (`objective`, `source`, `confidence`, wearable metadata).
- Direct submission to core (`--core-url`) or bridge (`--bridge-url`).
- Bridge admin session leasing (`--admin-token`) with scoped short-lived tokens.
- Optional pre-allowlist for new device IDs (`--ensure-device-allowlisted --session-device-id ...`).
- Optional status polling for async jobs/plans (`--wait`).

## Halo / Omi

`wearables/halo_bridge.py`

```bash
PYTHONPATH=core:shared python3 wearables/halo_bridge.py \
  --bridge-url http://127.0.0.1:9797 \
  --admin-token YOUR_BRIDGE_ADMIN_TOKEN \
  --ensure-device-allowlisted \
  --session-device-id halo-glasses-1 \
  --objective "Open dashboard and summarize failed jobs" \
  --wait
```

## XREAL X1

`wearables/xreal_bridge.py`

```bash
PYTHONPATH=core:shared python3 wearables/xreal_bridge.py \
  --bridge-url http://127.0.0.1:9797 \
  --admin-token YOUR_BRIDGE_ADMIN_TOKEN \
  --ensure-device-allowlisted \
  --session-device-id xreal-x1-1 \
  --display-mode ar_overlay \
  --hand-tracking \
  --objective "Open Aetherion market status and summarize top listings" \
  --wait
```
