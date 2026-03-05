from __future__ import annotations

from .service import NovaAdaptService


def get_novaprime_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.novaprime_status())
    return 200


def get_novaprime_emotion(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.novaprime_emotion_get())
    return 200


def get_novaprime_mesh_balance(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    node_id = str(single(query, "node_id") or "").strip()
    handler._send_json(200, service.novaprime_mesh_balance(node_id))
    return 200


def get_novaprime_mesh_reputation(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    node_id = str(single(query, "node_id") or "").strip()
    handler._send_json(200, service.novaprime_mesh_reputation(node_id))
    return 200


def get_novaprime_mesh_peers(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.novaprime_mesh_peers())
    return 200


def get_novaprime_mesh_aetherion_state(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    refresh_raw = str(single(query, "refresh") or "").strip().lower()
    refresh = refresh_raw not in {"0", "false", "no", "off"}
    handler._send_json(200, service.novaprime_mesh_aetherion_state(refresh=refresh))
    return 200


def get_novaprime_marketplace_listings(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.novaprime_marketplace_listings())
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


def get_novaprime_imprinting_session(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    session_id = str(single(query, "session_id") or "").strip()
    handler._send_json(200, service.novaprime_imprinting_session(session_id))
    return 200


def get_novaprime_narrative_bond_history(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    adapt_id = str(single(query, "adapt_id") or "").strip()
    player_id = str(single(query, "player_id") or "").strip()
    raw_top_k = single(query, "top_k")
    top_k = int(raw_top_k) if raw_top_k is not None else 120
    handler._send_json(
        200,
        service.novaprime_narrative_bond_history(adapt_id, player_id, top_k=top_k),
    )
    return 200


def post_novaprime_mesh_credit(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    node_id = str(payload.get("node_id") or "").strip()
    amount = float(payload.get("amount", 0.0))
    handler._send_json(200, service.novaprime_mesh_credit(node_id, amount))
    return 200


def post_novaprime_reason_dual(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    task = str(payload.get("task") or "").strip()
    handler._send_json(200, service.novaprime_reason_dual(task))
    return 200


def post_novaprime_emotion(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    chemicals = payload.get("chemicals")
    handler._send_json(200, service.novaprime_emotion_set(chemicals if isinstance(chemicals, dict) else {}))
    return 200


def post_novaprime_mesh_transfer(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    from_node = str(payload.get("from_node") or "").strip()
    to_node = str(payload.get("to_node") or "").strip()
    amount = float(payload.get("amount", 0.0))
    handler._send_json(200, service.novaprime_mesh_transfer(from_node, to_node, amount))
    return 200


def post_novaprime_mesh_peer_register(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    node_id = str(payload.get("node_id") or "").strip()
    url = str(payload.get("url") or "").strip()
    raw_caps = payload.get("capabilities")
    capabilities = raw_caps if isinstance(raw_caps, list) else []
    handler._send_json(200, service.novaprime_mesh_peer_register(node_id, url, capabilities))
    return 200


def post_novaprime_mesh_compute_request(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    requester = str(payload.get("requester") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    units = float(payload.get("units", 0.0))
    unit_price = float(payload.get("unit_price", 0.0))
    handler._send_json(200, service.novaprime_mesh_compute_request(requester, provider, units, unit_price))
    return 200


def post_novaprime_mesh_compute_settle(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    request_id = str(payload.get("request_id") or "").strip()
    requester = str(payload.get("requester") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    units = float(payload.get("units", 0.0))
    unit_price = float(payload.get("unit_price", 0.0))
    status = str(payload.get("status") or "requested").strip()
    ts = str(payload.get("ts") or "").strip()
    handler._send_json(
        200,
        service.novaprime_mesh_compute_settle(
            request_id=request_id,
            requester=requester,
            provider=provider,
            units=units,
            unit_price=unit_price,
            status=status,
            ts=ts,
        ),
    )
    return 200


def post_novaprime_marketplace_list(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    capsule_id = str(payload.get("capsule_id") or "").strip()
    seller = str(payload.get("seller") or "").strip()
    price = float(payload.get("price", 0.0))
    title = str(payload.get("title") or "").strip()
    handler._send_json(200, service.novaprime_marketplace_list(capsule_id, seller, price, title))
    return 200


def post_novaprime_marketplace_buy(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    listing_id = str(payload.get("listing_id") or "").strip()
    buyer = str(payload.get("buyer") or "").strip()
    handler._send_json(200, service.novaprime_marketplace_buy(listing_id, buyer))
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


def post_novaprime_imprinting_start(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_id = str(payload.get("player_id") or "").strip()
    player_profile = payload.get("player_profile")
    ttl_sec = float(payload.get("ttl_sec", 1800.0))
    handler._send_json(
        200,
        service.novaprime_imprinting_start(
            player_id,
            player_profile if isinstance(player_profile, dict) else {},
            ttl_sec=ttl_sec,
        ),
    )
    return 200


def post_novaprime_imprinting_resolve(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    session_id = str(payload.get("session_id") or "").strip()
    accepted = bool(payload.get("accepted", False))
    adapt_id = str(payload.get("adapt_id") or "").strip()
    handler._send_json(
        200,
        service.novaprime_imprinting_resolve(session_id, accepted=accepted, adapt_id=adapt_id),
    )
    return 200


def post_novaprime_phase_evaluate(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_state = payload.get("player_state")
    narrative_state = payload.get("narrative_state")
    environment_state = payload.get("environment_state")
    adapt_id = str(payload.get("adapt_id") or "").strip()
    auto_presence_update = bool(payload.get("auto_presence_update", False))
    handler._send_json(
        200,
        service.novaprime_phase_evaluate(
            player_state if isinstance(player_state, dict) else {},
            narrative_state=narrative_state if isinstance(narrative_state, dict) else {},
            environment_state=environment_state if isinstance(environment_state, dict) else {},
            adapt_id=adapt_id,
            auto_presence_update=auto_presence_update,
        ),
    )
    return 200


def post_novaprime_void_create(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    player_id = str(payload.get("player_id") or "").strip()
    player_profile = payload.get("player_profile")
    seed = str(payload.get("seed") or "").strip()
    handler._send_json(
        200,
        service.novaprime_void_create(
            player_id,
            player_profile=player_profile if isinstance(player_profile, dict) else {},
            seed=seed,
        ),
    )
    return 200


def post_novaprime_void_tick(handler, service: NovaAdaptService, payload: dict[str, object]) -> int:
    state = payload.get("state")
    stimulus = payload.get("stimulus")
    tick = int(payload.get("tick", 1))
    handler._send_json(
        200,
        service.novaprime_void_tick(
            state if isinstance(state, dict) else {},
            stimulus=stimulus if isinstance(stimulus, dict) else {},
            tick=tick,
        ),
    )
    return 200
