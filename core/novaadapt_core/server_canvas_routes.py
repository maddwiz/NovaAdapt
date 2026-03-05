from __future__ import annotations

from .service import NovaAdaptService


def get_canvas_status(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    context = str(single(query, "context") or "api").strip() or "api"
    handler._send_json(200, service.canvas_status(context=context))
    return 200


def get_canvas_frames(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    session_id = str(single(query, "session_id") or single(query, "session") or "").strip()
    if not session_id:
        raise ValueError("'session_id' is required")
    limit = int(single(query, "limit") or 20)
    context = str(single(query, "context") or "api").strip() or "api"
    handler._send_json(
        200,
        service.canvas_frames(
            session_id,
            limit=max(1, min(200, limit)),
            context=context,
        ),
    )
    return 200


def post_canvas_render(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("'title' is required")
    session_id = str(payload.get("session_id") or payload.get("session") or "default").strip() or "default"
    sections_raw = payload.get("sections")
    sections = [dict(item) for item in sections_raw if isinstance(item, dict)] if isinstance(sections_raw, list) else []
    footer = str(payload.get("footer") or "").strip()
    metadata = payload.get("metadata")
    context = str(payload.get("context") or "api").strip() or "api"
    handler._send_json(
        200,
        service.canvas_render(
            title,
            session_id=session_id,
            sections=sections,
            footer=footer,
            metadata=metadata if isinstance(metadata, dict) else {},
            context=context,
        ),
    )
    return 200
