from __future__ import annotations

from .service import NovaAdaptService


def get_workflows_status(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    context = str(single(query, "context") or "api").strip() or "api"
    handler._send_json(200, service.workflows_status(context=context))
    return 200


def get_workflows_list(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    context = str(single(query, "context") or "api").strip() or "api"
    limit = int(single(query, "limit") or 50)
    status = str(single(query, "status") or "").strip()
    handler._send_json(
        200,
        service.workflows_list(
            limit=max(1, min(500, limit)),
            status=status,
            context=context,
        ),
    )
    return 200


def get_workflow_item(
    handler,
    service: NovaAdaptService,
    single,
    query: dict[str, list[str]],
) -> int:
    workflow_id = str(single(query, "workflow_id") or single(query, "id") or "").strip()
    if not workflow_id:
        raise ValueError("'workflow_id' is required")
    context = str(single(query, "context") or "api").strip() or "api"
    handler._send_json(200, service.workflows_get(workflow_id, context=context))
    return 200


def post_workflows_start(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    objective = str(payload.get("objective") or "").strip()
    if not objective:
        raise ValueError("'objective' is required")
    steps_raw = payload.get("steps")
    steps = [dict(item) for item in steps_raw if isinstance(item, dict)] if isinstance(steps_raw, list) else []
    metadata = payload.get("metadata")
    workflow_id = str(payload.get("workflow_id") or "").strip()
    context = str(payload.get("context") or "api").strip() or "api"
    handler._send_json(
        200,
        service.workflows_start(
            objective,
            steps=steps,
            metadata=metadata if isinstance(metadata, dict) else {},
            workflow_id=workflow_id,
            context=context,
        ),
    )
    return 200


def post_workflows_advance(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    workflow_id = str(payload.get("workflow_id") or "").strip()
    if not workflow_id:
        raise ValueError("'workflow_id' is required")
    result = payload.get("result")
    error = str(payload.get("error") or "").strip()
    context = str(payload.get("context") or "api").strip() or "api"
    handler._send_json(
        200,
        service.workflows_advance(
            workflow_id,
            result=result if isinstance(result, dict) else {},
            error=error,
            context=context,
        ),
    )
    return 200


def post_workflows_resume(
    handler,
    service: NovaAdaptService,
    payload: dict[str, object],
) -> int:
    workflow_id = str(payload.get("workflow_id") or "").strip()
    if not workflow_id:
        raise ValueError("'workflow_id' is required")
    context = str(payload.get("context") or "api").strip() or "api"
    handler._send_json(200, service.workflows_resume(workflow_id, context=context))
    return 200
