from __future__ import annotations

from .flags import coerce_bool
from .jobs import JobManager
from .service import NovaAdaptService


def get_runtime_governance(handler, service: NovaAdaptService, job_manager: JobManager) -> int:
    handler._send_json(200, service.runtime_governance_status(job_stats=job_manager.stats()))
    return 200


def post_runtime_governance(
    handler,
    service: NovaAdaptService,
    job_manager: JobManager,
    path: str,
    payload: dict[str, object],
) -> int:
    normalized: dict[str, object] = {}
    if "paused" in payload:
        normalized["paused"] = coerce_bool(payload.get("paused"), default=False)
    if "pause_reason" in payload:
        normalized["pause_reason"] = str(payload.get("pause_reason") or "")
    if "budget_limit_usd" in payload:
        raw_budget = payload.get("budget_limit_usd")
        normalized["budget_limit_usd"] = None if raw_budget is None else float(raw_budget)
    if "max_active_runs" in payload:
        raw_max = payload.get("max_active_runs")
        normalized["max_active_runs"] = None if raw_max is None else int(raw_max)
    normalized["reset_usage"] = coerce_bool(payload.get("reset_usage"), default=False)
    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=lambda: (
            200,
            service.runtime_governance_update(
                paused=normalized.get("paused") if "paused" in normalized else None,
                pause_reason=normalized.get("pause_reason") if "pause_reason" in normalized else None,
                budget_limit_usd=normalized.get("budget_limit_usd")
                if "budget_limit_usd" in normalized
                else object(),
                max_active_runs=normalized.get("max_active_runs") if "max_active_runs" in normalized else object(),
                reset_usage=bool(normalized.get("reset_usage")),
                job_stats=job_manager.stats(),
            ),
        ),
        category="runtime",
        action="governance_update",
        entity_type="runtime",
    )


def post_runtime_cancel_all_jobs(
    handler,
    service: NovaAdaptService,
    job_manager: JobManager,
    path: str,
    payload: dict[str, object],
) -> int:
    normalized: dict[str, object] = {
        "pause": coerce_bool(payload.get("pause"), default=False),
        "pause_reason": str(payload.get("pause_reason") or "").strip(),
    }

    def _cancel_all() -> tuple[int, dict[str, object]]:
        if bool(normalized["pause"]):
            service.runtime_governance_update(
                paused=True,
                pause_reason=str(normalized["pause_reason"] or "Runtime paused during cancel-all"),
                job_stats=job_manager.stats(),
            )
        out = job_manager.cancel_all()
        out["governance"] = service.runtime_governance_status(job_stats=job_manager.stats())
        return 200, out

    return handler._respond_idempotent(
        path=path,
        payload=normalized,
        operation=_cancel_all,
        category="runtime",
        action="cancel_all_jobs",
        entity_type="job",
    )
