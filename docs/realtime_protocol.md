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

### Terminal List

```json
{ "type": "terminal_list", "id": "term-1" }
```

### Terminal Start

```json
{
  "type": "terminal_start",
  "id": "term-2",
  "body": { "command": "bash", "cwd": "/Users/desmondpottle/Documents" }
}
```

### Terminal Poll Output

```json
{
  "type": "terminal_poll",
  "id": "term-3",
  "session_id": "term-abc",
  "since_seq": 0,
  "limit": 600
}
```

### Terminal Input

```json
{
  "type": "terminal_input",
  "id": "term-4",
  "session_id": "term-abc",
  "input": "pwd\n"
}
```

### Terminal Close

```json
{
  "type": "terminal_close",
  "id": "term-5",
  "session_id": "term-abc"
}
```

### Browser Status / Pages

```json
{ "type": "browser_status", "id": "browser-1" }
```

```json
{ "type": "browser_pages", "id": "browser-2" }
```

### Browser Actions

```json
{
  "type": "browser_navigate",
  "id": "browser-3",
  "body": { "url": "https://example.com" },
  "idempotency_key": "idem-browser-nav-1"
}
```

```json
{
  "type": "browser_click",
  "id": "browser-4",
  "body": { "selector": "button.submit" },
  "idempotency_key": "idem-browser-click-1"
}
```

```json
{
  "type": "browser_fill",
  "id": "browser-5",
  "body": { "selector": "input[name=email]", "value": "user@example.com" },
  "idempotency_key": "idem-browser-fill-1"
}
```

```json
{
  "type": "browser_extract_text",
  "id": "browser-6",
  "body": { "selector": "h1" }
}
```

```json
{
  "type": "browser_screenshot",
  "id": "browser-7",
  "body": { "path": "shot.png", "full_page": true }
}
```

```json
{
  "type": "browser_wait_for_selector",
  "id": "browser-8",
  "body": { "selector": "#ready", "state": "visible" }
}
```

```json
{
  "type": "browser_evaluate_js",
  "id": "browser-9",
  "body": { "script": "document.title" }
}
```

```json
{
  "type": "browser_action",
  "id": "browser-10",
  "body": { "type": "navigate", "target": "https://example.com" }
}
```

```json
{ "type": "browser_close", "id": "browser-11" }
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

### Terminal Sessions

```json
{
  "type": "terminal_sessions",
  "id": "term-1",
  "status": 200,
  "payload": [{ "id": "term-abc", "open": true }],
  "core_request_id": "core-trace-id",
  "request_id": "trace-id"
}
```

### Terminal Started

```json
{
  "type": "terminal_started",
  "id": "term-2",
  "status": 201,
  "payload": { "id": "term-abc", "open": true },
  "core_request_id": "core-trace-id",
  "request_id": "trace-id"
}
```

### Terminal Output

```json
{
  "type": "terminal_output",
  "id": "term-3",
  "session_id": "term-abc",
  "status": 200,
  "payload": {
    "id": "term-abc",
    "open": true,
    "next_seq": 14,
    "chunks": [{ "seq": 14, "data": "$ ", "stream": "stdout" }]
  },
  "core_request_id": "core-trace-id",
  "request_id": "trace-id"
}
```

### Terminal Input Result / Closed

```json
{
  "type": "terminal_input_result",
  "id": "term-4",
  "session_id": "term-abc",
  "status": 200,
  "payload": { "id": "term-abc", "accepted": true },
  "request_id": "trace-id"
}
```

### Browser Result Envelopes

```json
{
  "type": "browser_status",
  "id": "browser-1",
  "status": 200,
  "payload": { "ok": true, "browser": "chromium", "headless": true },
  "core_request_id": "core-trace-id",
  "request_id": "trace-id"
}
```

```json
{
  "type": "browser_navigate_result",
  "id": "browser-3",
  "status": 200,
  "payload": { "status": "ok", "output": "navigated" },
  "idempotency_key": "idem-browser-nav-1",
  "replayed": false,
  "core_request_id": "core-trace-id",
  "request_id": "trace-id"
}
```

```json
{
  "type": "browser_closed",
  "id": "browser-11",
  "status": 200,
  "payload": { "status": "ok", "output": "closed" },
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

- `read`: `/health`, `/models`, `/history`, `/events`, `/plugins`, `/plugins/{name}/health`, `/memory/status`, `/memory/recall`, `/terminal/sessions`, `/terminal/sessions/{id}`, `/terminal/sessions/{id}/output`, `/browser/status`, `/browser/pages`, websocket audit stream
- `run`: `/run`, `/run_async`, `/swarm/run`, `/feedback`, `/memory/ingest`, `/terminal/sessions` (POST), `/terminal/sessions/{id}/input`, `/terminal/sessions/{id}/close`, `/plugins/{name}/call`, `/browser/action`, `/browser/navigate`, `/browser/click`, `/browser/fill`, `/browser/extract_text`, `/browser/screenshot`, `/browser/wait_for_selector`, `/browser/evaluate_js`, `/browser/close`
- `plan`: `/plans`, `/plans/{id}`
- `approve`: `/plans/{id}/approve`, `/plans/{id}/approve_async`, `/plans/{id}/retry_failed_async`, `/plans/{id}/retry_failed`
- `reject`: `/plans/{id}/reject`
- `undo`: `/undo`, `/plans/{id}/undo`
- `cancel`: `/jobs/{id}/cancel`
- `admin`: `/auth/session`, `/auth/session/revoke`, `/auth/devices`, `/auth/devices/remove`
