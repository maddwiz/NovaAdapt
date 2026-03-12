from __future__ import annotations

from .flags import coerce_bool
from .service import NovaAdaptService


def get_agent_templates(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    limit = int(single(query, "limit") or 50)
    source = str(single(query, "source") or "").strip()
    tag = str(single(query, "tag") or "").strip()
    handler._send_json(
        200,
        service.agent_templates_list(limit=max(1, min(500, limit)), source=source, tag=tag),
    )
    return 200


def get_agent_templates_gallery(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    tag = str(single(query, "tag") or "").strip()
    handler._send_json(200, service.agent_templates_gallery(tag=tag))
    return 200


def get_agent_template_item(
    handler,
    service: NovaAdaptService,
    path: str,
) -> int:
    prefix = "/agents/templates/"
    template_id = path[len(prefix) :].strip()
    if not template_id:
        raise ValueError("'template_id' is required")
    handler._send_json(200, service.agent_template_get(template_id))
    return 200


def get_agent_template_shared(
    handler,
    service: NovaAdaptService,
    path: str,
) -> int:
    prefix = "/agents/templates/shared/"
    share_token = path[len(prefix) :].strip()
    if not share_token:
        raise ValueError("'share_token' is required")
    handler._send_json(200, service.agent_template_shared(share_token))
    return 200


def post_agent_template_export(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    normalized = {
        "name": str(payload.get("name") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "objective": str(payload.get("objective") or "").strip(),
        "strategy": str(payload.get("strategy") or "single").strip() or "single",
        "candidates": _name_list(payload.get("candidates")),
        "steps": [dict(item) for item in payload.get("steps", []) if isinstance(item, dict)]
        if isinstance(payload.get("steps"), list)
        else [],
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        "tags": _name_list(payload.get("tags")),
        "workflow_id": str(payload.get("workflow_id") or "").strip(),
        "template_id": str(payload.get("template_id") or "").strip(),
        "include_memory": coerce_bool(payload.get("include_memory"), default=True),
        "memory_query": str(payload.get("memory_query") or "").strip(),
        "memory_top_k": int(payload.get("memory_top_k") or 5),
        "source": str(payload.get("source") or "local").strip() or "local",
    }
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (200, service.agent_template_export(**normalized)),
        category="agent_templates",
        action="export",
        entity_type="agent_template",
        entity_id_key="template_id",
    )


def post_agent_template_import(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.agent_template_import(payload)),
        category="agent_templates",
        action="import",
        entity_type="agent_template",
        entity_id_key="template_id",
    )


def post_agent_template_share(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    prefix = "/agents/templates/"
    suffix = "/share"
    template_id = path[len(prefix) : -len(suffix)].strip()
    if not template_id:
        raise ValueError("'template_id' is required")
    normalized = {
        "template_id": template_id,
        "rotate": coerce_bool(payload.get("rotate"), default=False),
        "shared": coerce_bool(payload.get("shared"), default=True),
    }
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (200, service.agent_template_share(**normalized)),
        category="agent_templates",
        action="share",
        entity_type="agent_template",
        entity_id=template_id,
    )


def post_agent_template_launch(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    prefix = "/agents/templates/"
    suffix = "/launch"
    template_id = path[len(prefix) : -len(suffix)].strip()
    if not template_id:
        raise ValueError("'template_id' is required")
    normalized = {
        "template_id": template_id,
        "mode": str(payload.get("mode") or "plan").strip() or "plan",
        "execute": coerce_bool(payload.get("execute"), default=False),
        "allow_dangerous": coerce_bool(payload.get("allow_dangerous"), default=False),
        "context": str(payload.get("context") or "api").strip() or "api",
        "overrides": payload.get("overrides") if isinstance(payload.get("overrides"), dict) else {},
    }
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (
            200,
            service.agent_template_launch(
                normalized["template_id"],
                mode=str(normalized["mode"]),
                execute=bool(normalized["execute"]),
                allow_dangerous=bool(normalized["allow_dangerous"]),
                context=str(normalized["context"]),
                overrides=dict(normalized["overrides"]),
            ),
        ),
        category="agent_templates",
        action="launch",
        entity_type="agent_template",
        entity_id=template_id,
    )


def _name_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
