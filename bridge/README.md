# bridge

Secure relay service for remote clients (phone/glasses) to reach NovaAdapt core.

## Current MVP

- Python relay package: `novaadapt_bridge.relay`
- Token-authenticated ingress (bridge token)
- Token-authenticated upstream calls to core API (core token)
- Forwards endpoints:
  - `GET /models`
  - `GET /history`
  - `GET /jobs` and `GET /jobs/{id}`
  - `POST /run`
  - `POST /run_async`
  - `POST /undo`
  - `POST /check`

## Run

```bash
novaadapt-bridge \
  --host 127.0.0.1 \
  --port 9797 \
  --core-url http://127.0.0.1:8787 \
  --bridge-token your_bridge_token \
  --core-token your_core_api_token
```

Environment variables are also supported:

- `NOVAADAPT_BRIDGE_HOST`
- `NOVAADAPT_BRIDGE_PORT`
- `NOVAADAPT_CORE_URL`
- `NOVAADAPT_BRIDGE_TOKEN`
- `NOVAADAPT_CORE_TOKEN`
- `NOVAADAPT_BRIDGE_TIMEOUT`
