from __future__ import annotations

from .service import NovaAdaptService


def get_memory_status(handler, service: NovaAdaptService) -> int:
    handler._send_json(200, service.memory_status())
    return 200


def post_memory_recall(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    query = str(payload.get("query") or "").strip()
    top_k = int(payload.get("top_k", 10))
    out = service.memory_recall(query, top_k=max(1, min(100, top_k)))
    handler._send_json(200, out)
    return 200


def post_memory_ingest(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (
            200,
            service.memory_ingest(
                str(payload.get("text") or ""),
                source_id=str(payload.get("source_id") or ""),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
            ),
        ),
        category="memory",
        action="ingest",
        entity_type="memory",
    )
