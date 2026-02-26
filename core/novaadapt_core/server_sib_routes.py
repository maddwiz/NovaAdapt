from __future__ import annotations

from .service import NovaAdaptService


def get_sib_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.sib_status())
    return 200


def post_sib_realm(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_id = str(payload.get("player_id") or "").strip()
    realm = str(payload.get("realm") or "").strip()
    handler._send_json(200, service.sib_realm(player_id, realm))
    return 200


def post_sib_companion_state(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    state = payload.get("state")
    handler._send_json(200, service.sib_companion_state(adapt_id, state if isinstance(state, dict) else {}))
    return 200


def post_sib_companion_speak(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    adapt_id = str(payload.get("adapt_id") or "").strip()
    text = str(payload.get("text") or "").strip()
    channel = str(payload.get("channel") or "in_game").strip() or "in_game"
    handler._send_json(200, service.sib_companion_speak(adapt_id, text, channel=channel))
    return 200


def post_sib_phase_event(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    event_type = str(payload.get("event_type") or "").strip()
    body = payload.get("payload")
    handler._send_json(200, service.sib_phase_event(event_type, body if isinstance(body, dict) else None))
    return 200


def post_sib_resonance_start(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_id = str(payload.get("player_id") or "").strip()
    player_profile = payload.get("player_profile")
    handler._send_json(
        200,
        service.sib_resonance_start(player_id, player_profile if isinstance(player_profile, dict) else None),
    )
    return 200


def post_sib_resonance_result(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_id = str(payload.get("player_id") or "").strip()
    adapt_id = str(payload.get("adapt_id") or "").strip()
    accepted = bool(payload.get("accepted", False))
    handler._send_json(200, service.sib_resonance_result(player_id, adapt_id, accepted))
    return 200
