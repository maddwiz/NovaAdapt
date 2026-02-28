from __future__ import annotations

from .service import NovaAdaptService


def _channel_from_path(path: str, suffix: str) -> str:
    return path.removeprefix("/channels/").removesuffix(f"/{suffix}").strip("/")


def get_channels(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.channels())
    return 200


def get_channel_health(
    handler,
    service: NovaAdaptService,
    path: str,
) -> int:
    channel_name = _channel_from_path(path, "health")
    if not channel_name:
        handler._send_json(404, {"error": "Not found"})
        return 404
    handler._send_json(200, service.channel_health(channel_name))
    return 200


def post_channel_send(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    channel_name = _channel_from_path(path, "send")
    if not channel_name:
        handler._send_json(404, {"error": "Not found"})
        return 404
    to = str(payload.get("to") or "").strip()
    text = str(payload.get("text") or "").strip()
    metadata = payload.get("metadata")
    if not to:
        raise ValueError("'to' is required")
    if not text:
        raise ValueError("'text' is required")
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (
            200,
            service.channel_send(
                channel_name,
                to,
                text,
                metadata=metadata if isinstance(metadata, dict) else None,
            ),
        ),
        category="channels",
        action="send",
        entity_type="channel",
        entity_id=channel_name,
    )


def post_channel_inbound(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    channel_name = _channel_from_path(path, "inbound")
    if not channel_name:
        handler._send_json(404, {"error": "Not found"})
        return 404
    inbound_payload = payload.get("payload")
    if not isinstance(inbound_payload, dict):
        raise ValueError("'payload' must be an object")
    if "auth_token" in payload and "auth_token" not in inbound_payload:
        inbound_payload = dict(inbound_payload)
        inbound_payload["auth_token"] = str(payload.get("auth_token") or "").strip()
    adapt_id = str(payload.get("adapt_id") or "").strip()
    auto_run = bool(payload.get("auto_run", False))
    execute = bool(payload.get("execute", False))
    request_headers = {str(k): str(v) for k, v in dict(handler.headers).items()}

    def _operation() -> tuple[int, dict[str, object]]:
        result = service.channel_inbound(
            channel_name,
            inbound_payload,
            adapt_id=adapt_id,
            auto_run=auto_run,
            execute=execute,
            request_headers=request_headers,
        )
        if isinstance(result, dict):
            return int(result.get("status_code") or 200), result
        return 200, {}

    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=_operation,
        category="channels",
        action="inbound",
        entity_type="channel",
        entity_id=channel_name,
    )
