# bridge

Secure relay service for remote clients (phone/glasses) to reach NovaAdapt core.

## Implementation

- Primary implementation: Go (`bridge/cmd/novaadapt-bridge`)
- Token-authenticated ingress (bridge token)
- Optional scoped session token issuance (`POST /auth/session`) for least-privilege clients
- Optional trusted-device allowlist via `X-Device-ID`
- Optional cross-origin browser allowlist (`--cors-allowed-origins`)
- Optional trusted proxy CIDR allowlist for `X-Forwarded-For` / `X-Forwarded-Proto` (`--trusted-proxy-cidrs`)
- Optional per-client rate limiting (`--rate-limit-rps`, `--rate-limit-burst`)
- Optional concurrent websocket connection cap (`--max-ws-connections`)
- Optional persisted session-revocation store (`--revocation-store-path`)
- Token-authenticated upstream calls to core API (core token)
- Request-id tracing (`X-Request-ID`) propagated to core
- Idempotency key forwarding (`Idempotency-Key`) propagated to core
- Optional deep health probe (`/health?deep=1`) to verify core reachability
- Deep health requires upstream core `/health` to return `2xx` (non-2xx marks bridge unready)
- Deep health payload includes bridge runtime state (rate-limit config, tracked clients, revoked session count)
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
  - `POST /plans/{id}/retry_failed`
  - `POST /plans/{id}/reject`
  - `POST /plans/{id}/undo`
  - `POST /run`
  - `POST /run_async`
  - `POST /undo`
  - `POST /check`
- `GET /ws` (WebSocket upgrade; requires bridge auth)
- `POST /auth/session` (issue scoped short-lived bridge session token; admin only)
- `POST /auth/session/revoke` (revoke a scoped session token; admin only)

## Auth Model

Bridge supports two token modes:

- Static bridge token (`NOVAADAPT_BRIDGE_TOKEN`): full admin capabilities.
- Signed session token (`na1.<payload>.<sig>`): scoped and time-limited.

`POST /auth/session` requires admin auth (static token, or session token with `admin` scope).
For cross-origin browser clients, set `--cors-allowed-origins` (or `NOVAADAPT_BRIDGE_CORS_ALLOWED_ORIGINS`).

Request body (all fields optional):

```json
{
  "subject": "iphone-operator",
  "scopes": ["read", "plan", "approve"],
  "device_id": "iphone-1",
  "ttl_seconds": 900
}
```

Response includes:

- `token` (session bearer token)
- `session_id` (token JTI; revocation handle)
- `expires_at`, `issued_at`
- normalized `scopes`, `subject`, `device_id`

Supported scopes:

- `admin` (all routes)
- `read` (GET routes + websocket connection)
- `run` (`/run`, `/run_async`, `/check`, and other non-plan POST routes)
- `plan` (`POST /plans`)
- `approve` (`POST /plans/{id}/approve`, `POST /plans/{id}/approve_async`, `POST /plans/{id}/retry_failed`)
- `reject` (`POST /plans/{id}/reject`)
- `undo` (`POST /undo`, `POST /plans/{id}/undo`)
- `cancel` (`POST /jobs/{id}/cancel`)

Unknown scopes are rejected at token-issue time with `400`.

Session revocation:

```json
{
  "token": "na1...."
}
```

Or revoke by session id:

```json
{
  "session_id": "abc123...",
  "expires_at": 1730000000
}
```

`POST /auth/session/revoke` adds the token `session_id` to an in-memory denylist until expiry.
If `--revocation-store-path` is configured, revocations survive bridge restart.

## WebSocket Channel (`/ws`)

`/ws` provides a single authenticated real-time channel for remote clients.

Server-to-client message types:

- `hello` - initial handshake metadata.
- `event` - forwarded audit events from core (`/events/stream`).
- `command_result` - response for an issued command (includes `core_request_id`, `idempotency_key`, `replayed`).
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

Browser-compatible websocket auth:

- `ws://.../ws?token=BRIDGE_TOKEN`
- `ws://.../ws?token=SESSION_TOKEN` (scopes still enforced)
- with device allowlist enabled: `ws://.../ws?token=BRIDGE_TOKEN&device_id=iphone-1`
- with device-bound session token: `ws://.../ws?token=SESSION_TOKEN&device_id=iphone-1`

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
  --tls-cert-file ./certs/bridge.crt \
  --tls-key-file ./certs/bridge.key \
  --session-signing-key your_session_hmac_key \
  --session-token-ttl-seconds 900 \
  --cors-allowed-origins http://127.0.0.1:8088 \
  --trusted-proxy-cidrs 127.0.0.1/32 \
  --rate-limit-rps 20 \
  --rate-limit-burst 20 \
  --max-ws-connections 100 \
  --revocation-store-path ./data/revocations.json \
  --allowed-device-ids iphone-15-pro,halo-glasses-1 \
  --log-requests true
```

Environment variables are also supported:

- `NOVAADAPT_BRIDGE_HOST`
- `NOVAADAPT_BRIDGE_PORT`
- `NOVAADAPT_CORE_URL`
- `NOVAADAPT_BRIDGE_TOKEN`
- `NOVAADAPT_CORE_TOKEN`
- `NOVAADAPT_BRIDGE_TLS_CERT_FILE` (optional HTTPS cert PEM)
- `NOVAADAPT_BRIDGE_TLS_KEY_FILE` (optional HTTPS private key PEM; must be set with cert)
- `NOVAADAPT_BRIDGE_SESSION_SIGNING_KEY` (defaults to bridge token when unset)
- `NOVAADAPT_BRIDGE_SESSION_TTL_SECONDS` (default issued session TTL)
- `NOVAADAPT_BRIDGE_CORS_ALLOWED_ORIGINS` (comma-separated browser origins; `*` to allow any)
- `NOVAADAPT_BRIDGE_TRUSTED_PROXY_CIDRS` (comma-separated IP/CIDR list allowed to set `X-Forwarded-*` headers)
- `NOVAADAPT_BRIDGE_RATE_LIMIT_RPS` (per-client requests/second; `<=0` disables)
- `NOVAADAPT_BRIDGE_RATE_LIMIT_BURST` (per-client burst capacity)
- `NOVAADAPT_BRIDGE_MAX_WS_CONNECTIONS` (max concurrent websocket sessions; `0` disables cap)
- `NOVAADAPT_BRIDGE_REVOCATION_STORE_PATH` (optional persisted session revocation file)
- `NOVAADAPT_BRIDGE_ALLOWED_DEVICE_IDS` (comma-separated trusted device IDs)
- `NOVAADAPT_BRIDGE_TIMEOUT`
- `NOVAADAPT_BRIDGE_LOG_REQUESTS`

When TLS cert/key are configured, bridge serves HTTPS and websocket clients should use `wss://`.
