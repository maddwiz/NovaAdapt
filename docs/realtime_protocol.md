# Realtime Protocol

NovaAdapt bridge websocket protocol used by desktop/mobile/wearable clients.

## Endpoint

- `GET /ws`
- Auth: `Authorization: Bearer <token>` or query `?token=...`

## Client -> Bridge Messages

All messages are JSON objects.

### Initial Hello (server)

Immediately after websocket upgrade, bridge emits:

```json
{ "type": "hello", "request_id": "trace-id", "service": "novaadapt-bridge-go" }
```

### Ping

```json
{ "type": "ping", "id": "req-1" }
```

### Command

```json
{
  "type": "command",
  "id": "req-2",
  "method": "POST",
  "path": "/run_async",
  "body": { "objective": "Open browser and run smoke tests" }
}
```

### Set Audit Cursor

```json
{ "type": "set_since_id", "id": "req-3", "since_id": 120 }
```

## Bridge -> Client Messages

### Pong

```json
{ "type": "pong", "id": "req-1", "request_id": "trace-id" }
```

### Ack (for cursor updates)

```json
{
  "type": "ack",
  "id": "req-3",
  "since_id": 120,
  "request_id": "trace-id"
}
```

### Command Result

```json
{
  "type": "command_result",
  "id": "req-2",
  "status": 202,
  "payload": { "job_id": "...", "status": "queued" },
  "core_request_id": "core-trace-id",
  "idempotency_key": "idem-123",
  "replayed": false,
  "request_id": "trace-id"
}
```

### Event Stream Envelope

```json
{
  "type": "event",
  "event": "audit",
  "data": {
    "id": 121,
    "category": "run",
    "action": "run_async",
    "status": "ok",
    "request_id": "trace-id"
  },
  "request_id": "trace-id"
}
```

### Error

```json
{ "type": "error", "id": "req-2", "error": "forbidden by token scope" }
```

## Scope Mapping

- `read`: `/health`, `/models`, `/history`, `/events`, websocket audit stream
- `run`: `/run`, `/run_async`
- `plan`: `/plans`, `/plans/{id}`
- `approve`: `/plans/{id}/approve`, `/plans/{id}/approve_async`, `/plans/{id}/retry_failed_async`, `/plans/{id}/retry_failed`
- `reject`: `/plans/{id}/reject`
- `undo`: `/undo`, `/plans/{id}/undo`
- `cancel`: `/jobs/{id}/cancel`
- `admin`: `/auth/session`, `/auth/session/revoke`
