from __future__ import annotations

from typing import Any, Callable


IdempotentOperation = Callable[[], tuple[int, object]]


def idempotency_key(handler) -> str | None:
    value = str(handler.headers.get("Idempotency-Key", "")).strip()
    if value:
        return value
    return None


def execute_idempotent(
    handler,
    *,
    idempotency_store,
    is_idempotent_route: Callable[[str], bool],
    path: str,
    payload: dict[str, object],
    operation: IdempotentOperation,
) -> tuple[int, object, bool]:
    key = idempotency_key(handler)
    if idempotency_store is None or key is None or not is_idempotent_route(path):
        status_code, response_payload = operation()
        return int(status_code), response_payload, False

    state, record = idempotency_store.begin(
        key=key,
        method="POST",
        path=path,
        payload=payload,
    )
    if state == "replay":
        replay_status = int(record["status_code"]) if record else 200
        replay_payload = record["payload"] if record else {}
        return replay_status, replay_payload, True
    if state in {"conflict", "in_progress"}:
        error_payload: dict[str, Any] = {"error": record["error"] if record else "Idempotency conflict"}
        return 409, error_payload, False

    try:
        status_code, response_payload = operation()
    except Exception:
        idempotency_store.clear(key=key, method="POST", path=path)
        raise

    idempotency_store.complete(
        key=key,
        method="POST",
        path=path,
        status_code=int(status_code),
        payload=response_payload,
    )
    return int(status_code), response_payload, False


def respond_idempotent(
    handler,
    *,
    idempotency_store,
    is_idempotent_route: Callable[[str], bool],
    path: str,
    payload: dict[str, object],
    operation: IdempotentOperation,
    category: str,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    entity_id_key: str | None = None,
) -> int:
    status_code, response_payload, replayed = execute_idempotent(
        handler,
        idempotency_store=idempotency_store,
        is_idempotent_route=is_idempotent_route,
        path=path,
        payload=payload,
        operation=operation,
    )

    resolved_entity_id = entity_id
    if resolved_entity_id is None and entity_id_key and isinstance(response_payload, dict):
        raw_entity = response_payload.get(entity_id_key)
        if raw_entity is not None:
            resolved_entity_id = str(raw_entity)

    handler._audit_event(
        category=category,
        action=action,
        status="replayed" if replayed else ("ok" if status_code < 400 else "error"),
        entity_type=entity_type,
        entity_id=resolved_entity_id,
        payload=response_payload if isinstance(response_payload, dict) else None,
    )
    handler._send_json(
        status_code,
        response_payload,
        replayed=replayed,
        idempotency_key=idempotency_key(handler),
    )
    return int(status_code)
