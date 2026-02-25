# Realtime Protocol

NovaAdapt bridge websocket protocol used by desktop/mobile/wearable clients.

## Endpoint

- `GET /ws`
- Auth: `Authorization: Bearer <token>` or query `?token=...`

## Client -> Bridge Messages

All messages are JSON objects.

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

### Seek Audit Cursor

```json
{ "type": "seek", "id": "req-3", "since_id": 120 }
```

## Bridge -> Client Messages

### Ack

```json
{ "type": "ack", "id": "req-2", "request_id": "trace-id" }
```

### Command Result

```json
{
  "type": "result",
  "id": "req-2",
  "status": 202,
  "body": { "job_id": "...", "status": "queued" }
}
```

### Audit Event Stream

```json
{
  "type": "audit",
  "since_id": 121,
  "event": {
    "id": 121,
    "category": "run",
    "action": "run_async",
    "status": "ok",
    "request_id": "trace-id"
  }
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
- `approve`: `/plans/{id}/approve`, `/plans/{id}/approve_async`
- `reject`: `/plans/{id}/reject`
- `undo`: `/undo`, `/plans/{id}/undo`
- `cancel`: `/jobs/{id}/cancel`
- `admin`: `/auth/session`, `/auth/session/revoke`
