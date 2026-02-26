from __future__ import annotations

from .service import NovaAdaptService


def get_novaprime_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.novaprime_status())
    return 200


def get_novaprime_identity_profile(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    adapt_id = str(single(query, "adapt_id") or "").strip()
    handler._send_json(200, service.novaprime_identity_profile(adapt_id))
    return 200


def get_novaprime_presence(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    adapt_id = str(single(query, "adapt_id") or "").strip()
    handler._send_json(200, service.novaprime_presence_get(adapt_id))
    return 200


def post_novaprime_identity_bond(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    player_id = str(payload.get("player_id") or "").strip()
    element = str(payload.get("element") or "").strip()
    subclass = str(payload.get("subclass") or "").strip()
    handler._send_json(
        200,
        service.novaprime_identity_bond(
            adapt_id,
            player_id,
            element=element,
            subclass=subclass,
        ),
    )
    return 200


def post_novaprime_identity_verify(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    player_id = str(payload.get("player_id") or "").strip()
    handler._send_json(200, service.novaprime_identity_verify(adapt_id, player_id))
    return 200


def post_novaprime_identity_evolve(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    xp_gain = float(payload.get("xp_gain", 0.0))
    new_skill = str(payload.get("new_skill") or "").strip()
    handler._send_json(
        200,
        service.novaprime_identity_evolve(
            adapt_id,
            xp_gain=xp_gain,
            new_skill=new_skill,
        ),
    )
    return 200


def post_novaprime_presence_update(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    realm = str(payload.get("realm") or "").strip()
    activity = str(payload.get("activity") or "").strip()
    handler._send_json(
        200,
        service.novaprime_presence_update(
            adapt_id,
            realm=realm,
            activity=activity,
        ),
    )
    return 200


def post_novaprime_resonance_score(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_profile = payload.get("player_profile")
    handler._send_json(
        200,
        service.novaprime_resonance_score(player_profile if isinstance(player_profile, dict) else {}),
    )
    return 200


def post_novaprime_resonance_bond(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_id = str(payload.get("player_id") or "").strip()
    player_profile = payload.get("player_profile")
    adapt_id = str(payload.get("adapt_id") or "").strip()
    handler._send_json(
        200,
        service.novaprime_resonance_bond(
            player_id,
            player_profile if isinstance(player_profile, dict) else None,
            adapt_id=adapt_id,
        ),
    )
    return 200
