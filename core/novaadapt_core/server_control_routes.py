from __future__ import annotations

import base64

from .flags import coerce_bool
from .service import NovaAdaptService


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


def get_homeassistant_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.homeassistant_status())
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
