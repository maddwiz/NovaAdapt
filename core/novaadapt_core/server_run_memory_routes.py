from __future__ import annotations

from typing import Callable

from .jobs import JobManager
from .service import NovaAdaptService


def post_run(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.run(payload)),
        category="run",
        action="run",
    )


def post_run_async(
    handler,
    service: NovaAdaptService,
    job_manager: JobManager,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (
            202,
            {
                "job_id": job_manager.submit(service.run, payload),
                "status": "queued",
            },
        ),
        category="run",
        action="run_async",
        entity_type="job",
        entity_id_key="job_id",
    )


def post_swarm_run(
    handler,
    service: NovaAdaptService,
    job_manager: JobManager,
    path: str,
    payload: dict[str, object],
) -> int:
    objectives = payload.get("objectives")
    if not isinstance(objectives, list):
        raise ValueError("'objectives' must be an array")
    normalized_objectives = [str(item).strip() for item in objectives if str(item).strip()]
    if not normalized_objectives:
        raise ValueError("'objectives' must contain at least one non-empty objective")

    requested_max_agents = int(payload.get("max_agents", len(normalized_objectives)))
    max_agents = min(32, max(1, requested_max_agents))
    selected = normalized_objectives[:max_agents]

    shared_payload = {
        "strategy": payload.get("strategy", "single"),
        "model": payload.get("model"),
        "candidates": payload.get("candidates"),
        "fallbacks": payload.get("fallbacks"),
        "execute": bool(payload.get("execute", False)),
        "allow_dangerous": bool(payload.get("allow_dangerous", False)),
        "max_actions": int(payload.get("max_actions", 25)),
        "adapt_id": payload.get("adapt_id"),
        "player_id": payload.get("player_id"),
        "realm": payload.get("realm"),
        "activity": payload.get("activity"),
        "post_realm": payload.get("post_realm"),
        "post_activity": payload.get("post_activity"),
    }

    def _run_swarm() -> tuple[int, dict[str, object]]:
        jobs: list[dict[str, object]] = []
        for idx, objective in enumerate(selected, start=1):
            run_payload = dict(shared_payload)
            run_payload["objective"] = objective
            job_id = job_manager.submit(service.run, run_payload)
            jobs.append({"index": idx, "objective": objective, "job_id": job_id})
        return (
            202,
            {
                "status": "queued",
                "kind": "swarm",
                "total_objectives": len(normalized_objectives),
                "submitted_jobs": len(jobs),
                "jobs": jobs,
            },
        )

    return handler._respond_idempotent(
        path=path,
        payload={**payload, "objectives": selected},
        operation=_run_swarm,
        category="swarm",
        action="run",
        entity_type="swarm",
    )


def post_undo(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.undo(payload)),
        category="undo",
        action="undo",
        entity_type="action",
        entity_id_key="id",
    )


def post_check(
    handler,
    service: NovaAdaptService,
    parse_name_list: Callable[[object], list[str]],
    to_path: Callable[[object], object],
    payload: dict[str, object],
) -> int:
    model_names = parse_name_list(payload.get("models"))
    probe_prompt = str(payload.get("probe") or "Reply with: OK")
    out = service.check(
        config_path=to_path(payload.get("config")),
        model_names=model_names or None,
        probe_prompt=probe_prompt,
    )
    handler._send_json(200, out)
    return 200


def post_feedback(
    handler,
    service: NovaAdaptService,
    path: str,
    payload: dict[str, object],
) -> int:
    return handler._respond_idempotent(
        path=path,
        payload=payload,
        operation=lambda: (200, service.record_feedback(payload)),
        category="feedback",
        action="record",
        entity_type="feedback",
        entity_id_key="id",
    )
