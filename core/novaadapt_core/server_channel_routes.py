from __future__ import annotations

import os

from .flags import coerce_bool
from .service import NovaAdaptService

_DIRECT_WEBHOOK_CHANNELS = {"discord", "slack", "whatsapp", "messenger", "instagram", "telegram", "signal", "sms"}
_META_CHALLENGE_CHANNELS = {"whatsapp", "messenger", "instagram"}


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


def get_channel_inbound(
    handler,
    service: NovaAdaptService,
    single,
    path: str,
    query: dict[str, list[str]],
) -> int:
    channel_name = _channel_from_path(path, "inbound")
    if not channel_name:
        handler._send_json(404, {"error": "Not found"})
        return 404

    resolved = service.channel_registry.resolve_name(channel_name)
    if resolved not in _META_CHALLENGE_CHANNELS:
        handler._send_json(405, {"error": f"GET inbound not supported for channel: {resolved}"})
        return 405

    mode = str(single(query, "hub.mode") or "").strip().lower()
    challenge = str(single(query, "hub.challenge") or "").strip()
    provided_token = str(single(query, "hub.verify_token") or "").strip()
    if mode != "subscribe" or not challenge:
        handler._send_json(
            400,
            {
                "ok": False,
                "channel": resolved,
                "error": "missing required challenge params: hub.mode=subscribe and hub.challenge",
            },
        )
        return 400

    expected_token = str(os.getenv(f"NOVAADAPT_CHANNEL_{resolved.upper()}_VERIFY_TOKEN", "")).strip()
    if not expected_token:
        handler._send_json(
            503,
            {
                "ok": False,
                "channel": resolved,
                "error": f"webhook verify token not configured for {resolved}",
            },
        )
        return 503
    if not provided_token or provided_token != expected_token:
        handler._send_json(
            403,
            {
                "ok": False,
                "channel": resolved,
                "error": "invalid webhook verify token",
            },
        )
        return 403

    body = challenge.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("X-Request-ID", handler._request_id)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
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
    if isinstance(inbound_payload, dict):
        normalized_payload = inbound_payload
    elif channel_name in _DIRECT_WEBHOOK_CHANNELS:
        # Provider webhook mode accepts direct payload body at /channels/{channel}/inbound.
        normalized_payload = payload
    else:
        raise ValueError("'payload' must be an object")
    if "auth_token" in payload and "auth_token" not in normalized_payload:
        normalized_payload = dict(normalized_payload)
        normalized_payload["auth_token"] = str(payload.get("auth_token") or "").strip()
    adapt_id = str(payload.get("adapt_id") or "").strip()
    auto_run = coerce_bool(payload.get("auto_run"), default=False)
    execute = coerce_bool(payload.get("execute"), default=False)
    request_headers = {str(k): str(v) for k, v in dict(handler.headers).items()}
    request_body_text = getattr(handler, "_last_raw_body", "")

    def _operation() -> tuple[int, dict[str, object]]:
        result = service.channel_inbound(
            channel_name,
            normalized_payload,
            adapt_id=adapt_id,
            auto_run=auto_run,
            execute=execute,
            request_headers=request_headers,
            request_body_text=request_body_text if isinstance(request_body_text, str) else None,
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
