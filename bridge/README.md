# bridge

Secure relay service for remote clients (phone/glasses) to reach NovaAdapt core.

## Implementation

- Primary implementation: Go (`bridge/cmd/novaadapt-bridge`)
- Token-authenticated ingress (bridge token)
- Token-authenticated upstream calls to core API (core token)
- Request-id tracing (`X-Request-ID`) propagated to core
- Optional deep health probe (`/health?deep=1`) to verify core reachability
- Graceful shutdown on `SIGINT`/`SIGTERM`
- Forwards endpoints:
  - `GET /models`
  - `GET /history`
  - `GET /jobs` and `GET /jobs/{id}`
  - `POST /run`
  - `POST /run_async`
  - `POST /undo`
  - `POST /check`

## Build

```bash
cd bridge
go test ./...
go build -o ./bin/novaadapt-bridge ./cmd/novaadapt-bridge
```

Or from repo root:

```bash
make build-bridge
```

## Run

```bash
./bridge/bin/novaadapt-bridge \
  --host 127.0.0.1 \
  --port 9797 \
  --core-url http://127.0.0.1:8787 \
  --bridge-token your_bridge_token \
  --core-token your_core_api_token \
  --log-requests true
```

Environment variables are also supported:

- `NOVAADAPT_BRIDGE_HOST`
- `NOVAADAPT_BRIDGE_PORT`
- `NOVAADAPT_CORE_URL`
- `NOVAADAPT_BRIDGE_TOKEN`
- `NOVAADAPT_CORE_TOKEN`
- `NOVAADAPT_BRIDGE_TIMEOUT`
- `NOVAADAPT_BRIDGE_LOG_REQUESTS`
