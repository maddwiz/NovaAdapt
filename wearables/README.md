# wearables

Wearable integration adapters for Halo/Omi style devices.

`wearables/halo_bridge.py` provides:

- Intent normalization (`objective`, `source`, `confidence`, wearable metadata).
- Direct submission to core (`--core-url`) or bridge (`--bridge-url`).
- Bridge admin session leasing (`--admin-token`) with scoped short-lived tokens.
- Optional pre-allowlist for new device IDs (`--ensure-device-allowlisted --session-device-id ...`).
- Optional status polling for async jobs/plans (`--wait`).

Example:

```bash
PYTHONPATH=core:shared python3 wearables/halo_bridge.py \
  --bridge-url http://127.0.0.1:9797 \
  --admin-token YOUR_BRIDGE_ADMIN_TOKEN \
  --ensure-device-allowlisted \
  --session-device-id halo-glasses-1 \
  --objective "Open dashboard and summarize failed jobs" \
  --wait
```
