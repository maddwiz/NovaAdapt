from __future__ import annotations

from .service import NovaAdaptService


def get_adapt_toggle(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    adapt_id = str(single(query, "adapt_id") or "").strip()
    if not adapt_id:
        raise ValueError("'adapt_id' is required")
    handler._send_json(200, service.adapt_toggle_get(adapt_id))
    return 200


def post_adapt_toggle(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    mode = str(payload.get("mode") or "").strip()
    source = str(payload.get("source") or "api").strip() or "api"
    if not adapt_id:
        raise ValueError("'adapt_id' is required")
    if not mode:
        raise ValueError("'mode' is required")
    handler._send_json(200, service.adapt_toggle_set(adapt_id, mode, source=source))
    return 200


def get_adapt_bond(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    adapt_id = str(single(query, "adapt_id") or "").strip()
    if not adapt_id:
        raise ValueError("'adapt_id' is required")
    cached = service.adapt_bond_get(adapt_id)
    handler._send_json(
        200,
        {
            "adapt_id": adapt_id,
            "cached": cached if isinstance(cached, dict) else None,
            "found": isinstance(cached, dict),
        },
    )
    return 200
