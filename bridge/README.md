# bridge

Secure relay service for remote clients (phone/glasses) to reach NovaAdapt core.

## Implementation

- Primary implementation: Go (`bridge/cmd/novaadapt-bridge`)
- Token-authenticated ingress (bridge token)
- Token-authenticated upstream calls to core API (core token)
- Request-id tracing (`X-Request-ID`) propagated to core
- Idempotency key forwarding (`Idempotency-Key`) propagated to core
- Optional deep health probe (`/health?deep=1`) to verify core reachability
- Graceful shutdown on `SIGINT`/`SIGTERM`
- Metrics endpoint (`/metrics`) for request/unauthorized/upstream-error counters
- WebSocket endpoint (`/ws`) for live event streaming + command/approval control
- Forwards endpoints:
  - `GET /openapi.json`
  - `GET /dashboard`
  - `GET /dashboard/data`
  - `GET /models`
  - `GET /history`
  - `GET /jobs` and `GET /jobs/{id}`
  - `GET /jobs/{id}/stream` (SSE passthrough)
  - `GET /plans/{id}/stream` (SSE passthrough)
  - `POST /jobs/{id}/cancel`
  - `GET /plans` and `GET /plans/{id}`
  - `POST /plans`
  - `POST /plans/{id}/approve`
  - `POST /plans/{id}/approve_async`
  - `POST /plans/{id}/reject`
  - `POST /plans/{id}/undo`
  - `POST /run`
  - `POST /run_async`
  - `POST /undo`
  - `POST /check`
  - `GET /ws` (WebSocket upgrade; requires bridge auth)

## WebSocket Channel (`/ws`)

`/ws` provides a single authenticated real-time channel for remote clients.

Server-to-client message types:

- `hello` - initial handshake metadata.
- `event` - forwarded audit events from core (`/events/stream`).
- `command_result` - response for an issued command.
- `ack`, `pong`, `error`.

Client-to-server message types:

- `ping` - health ping.
- `set_since_id` - move event cursor (`since_id`) for streamed events.
- `command` - execute authenticated core requests over the socket.

`command` shape:

```json
{
  "type": "command",
  "id": "approve-1",
  "method": "POST",
  "path": "/plans/plan1/approve_async",
  "body": {"execute": true},
  "idempotency_key": "idem-approve-1"
}
```

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

Container build uses:

- `/Users/desmondpottle/Documents/New project/NovaAdapt/deploy/docker/Dockerfile.bridge`

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
