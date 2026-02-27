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


def post_adapt_bond_verify(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    player_id = str(payload.get("player_id") or "").strip()
    refresh_profile = bool(payload.get("refresh_profile", True))
    if not adapt_id:
        raise ValueError("'adapt_id' is required")
    if not player_id:
        raise ValueError("'player_id' is required")
    handler._send_json(
        200,
        service.adapt_bond_verify(
            adapt_id,
            player_id,
            refresh_profile=refresh_profile,
        ),
    )
    return 200


def get_adapt_persona(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    adapt_id = str(single(query, "adapt_id") or "").strip()
    player_id = str(single(query, "player_id") or "").strip()
    if not adapt_id:
        raise ValueError("'adapt_id' is required")
    handler._send_json(
        200,
        service.adapt_persona_get(
            adapt_id,
            player_id=player_id,
        ),
    )
    return 200
