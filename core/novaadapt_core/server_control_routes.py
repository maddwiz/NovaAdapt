from __future__ import annotations

import base64

from .flags import coerce_bool
from .service import NovaAdaptService


def get_control_artifacts(handler, service: NovaAdaptService, single, query: dict[str, list[str]]) -> int:
    limit = int(single(query, "limit") or 10)
    control_type = single(query, "control_type")
    handler._send_json(
        200,
        service.list_control_artifacts(limit=max(1, limit), control_type=control_type),
    )
    return 200


def get_control_artifact_item(handler, service: NovaAdaptService, path: str) -> int:
    artifact_id = path.removeprefix("/control/artifacts/").strip("/")
    if not artifact_id:
        handler._send_json(404, {"error": "Artifact not found"})
        return 404
    item = service.get_control_artifact(artifact_id)
    if item is None:
        handler._send_json(404, {"error": "Artifact not found"})
        return 404
    handler._send_json(200, item)
    return 200


def get_control_artifact_preview(handler, service: NovaAdaptService, path: str) -> int:
    artifact_id = path.removeprefix("/control/artifacts/").removesuffix("/preview").strip("/")
    preview = service.control_artifact_preview(artifact_id)
    if preview is None:
        handler._send_json(404, {"error": "Artifact preview not found"})
        return 404
    payload, content_type = preview
    handler._send_bytes(200, payload, content_type=content_type)
    return 200


def post_execute_vision(handler, service: NovaAdaptService, path: str, payload: dict[str, object]) -> int:
    normalized = dict(payload)
    if payload.get("screenshot_base64") is not None:
        normalized["screenshot_base64"] = str(payload.get("screenshot_base64") or "")
    normalized["execute"] = coerce_bool(payload.get("execute"), default=False)
    normalized["allow_dangerous"] = coerce_bool(payload.get("allow_dangerous"), default=False)
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (200, service.vision_execute(normalized)),
        category="vision",
        action="execute",
        entity_type="vision",
    )


def post_mobile_action(handler, service: NovaAdaptService, path: str, payload: dict[str, object]) -> int:
    normalized = dict(payload)
    normalized["execute"] = coerce_bool(payload.get("execute"), default=False)
    normalized["allow_dangerous"] = coerce_bool(payload.get("allow_dangerous"), default=False)
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (200, service.mobile_action(normalized)),
        category="mobile",
        action="execute",
        entity_type="mobile",
    )


def get_mobile_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.mobile_status())
    return 200


def get_homeassistant_entities(handler, service: NovaAdaptService, single, query: dict[str, list[str]]) -> int:
    handler._send_json(
        200,
        service.homeassistant_discover(
            domain=str(single(query, "domain") or ""),
            entity_id_prefix=str(single(query, "entity_id_prefix") or ""),
            limit=int(single(query, "limit") or 250),
        ),
    )
    return 200


def get_homeassistant_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.homeassistant_status())
    return 200


def get_mqtt_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.mqtt_status())
    return 200


def post_homeassistant_action(handler, service: NovaAdaptService, path: str, payload: dict[str, object]) -> int:
    normalized = dict(payload)
    normalized["execute"] = coerce_bool(payload.get("execute"), default=False)
    normalized["allow_dangerous"] = coerce_bool(payload.get("allow_dangerous"), default=False)
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (200, service.homeassistant_action(normalized)),
        category="iot",
        action="execute",
        entity_type="homeassistant",
    )


def post_mqtt_publish(handler, service: NovaAdaptService, path: str, payload: dict[str, object]) -> int:
    normalized: dict[str, object] = {
        "action": {
            "type": "mqtt_publish",
            "topic": payload.get("topic"),
            "payload": payload.get("payload"),
            "qos": payload.get("qos"),
            "retain": coerce_bool(payload.get("retain"), default=False),
            "transport": payload.get("transport") or "mqtt-direct",
        },
        "execute": coerce_bool(payload.get("execute"), default=False),
        "allow_dangerous": coerce_bool(payload.get("allow_dangerous"), default=False),
    }
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (200, service.homeassistant_action(normalized)),
        category="iot",
        action="mqtt_publish",
        entity_type="mqtt",
    )


def post_mqtt_subscribe(handler, service: NovaAdaptService, path: str, payload: dict[str, object]) -> int:
    normalized: dict[str, object] = {
        "topic": str(payload.get("topic") or ""),
        "timeout_seconds": float(payload.get("timeout_seconds", 3.0) or 3.0),
        "max_messages": int(payload.get("max_messages", 10) or 10),
        "qos": int(payload.get("qos", 0) or 0),
    }
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (
            200,
            service.mqtt_subscribe(
                topic=str(normalized["topic"]),
                timeout_seconds=float(normalized["timeout_seconds"]),
                max_messages=int(normalized["max_messages"]),
                qos=int(normalized["qos"]),
            ),
        ),
        category="iot",
        action="mqtt_subscribe",
        entity_type="mqtt",
    )


def decode_screenshot_base64(value: object) -> bytes | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if "," in raw and raw.lower().startswith("data:image"):
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError("invalid screenshot_base64 payload") from exc
