from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timezone

from .audit_store import AuditStore
from .dashboard import render_canvas_workflows_html, render_dashboard_html
from .flags import coerce_bool
from .openapi import build_openapi_spec
from .service import NovaAdaptService


def _canvas_workflows_ui_enabled() -> bool:
    return coerce_bool(os.getenv("NOVAADAPT_ENABLE_CANVAS_WORKFLOWS_UI"), default=False)


def _parse_iso_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _timeline_bucket(value: object) -> str:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return "unknown"
    return parsed.astimezone(timezone.utc).strftime("%m-%d %H:00Z")


def _sorted_counter(counter: Counter[str], *, limit: int = 8) -> list[dict[str, object]]:
    return [
        {"label": label, "count": count}
        for label, count in counter.most_common(max(1, int(limit)))
    ]


def _sorted_timeline(
    rows: dict[str, dict[str, object]],
    *,
    sort_unknown_last: bool = True,
    limit: int = 8,
) -> list[dict[str, object]]:
    def _sort_key(item: tuple[str, dict[str, object]]) -> tuple[int, str]:
        label = item[0]
        if label == "unknown":
            return (1 if sort_unknown_last else -1, label)
        return (0, label)

    ordered = sorted(rows.items(), key=_sort_key)
    if len(ordered) > max(1, int(limit)):
        ordered = ordered[-max(1, int(limit)) :]
    return [{"bucket": bucket, **payload} for bucket, payload in ordered]


def _usage_call_count(usage: object) -> int:
    if not isinstance(usage, dict):
        return 0
    total = 0
    for item in usage.values():
        if not isinstance(item, dict):
            continue
        try:
            total += max(0, int(item.get("calls", 0) or 0))
        except Exception:
            continue
    return total


def _repair_rollup(repair: object, results: object) -> dict[str, object]:
    repair_obj = repair if isinstance(repair, dict) else {}
    attempted = bool(repair_obj)
    healed = bool(repair_obj.get("healed", False))
    failed = attempted and not healed
    domains: Counter[str] = Counter()
    attempts = repair_obj.get("attempts")
    if isinstance(attempts, list):
        for item in attempts:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "").strip().lower()
            if domain:
                domains[domain] += 1
    result_counts = Counter()
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip().lower() or "unknown"
            result_counts[status] += 1
    return {
        "attempted": attempted,
        "healed": healed,
        "failed": failed,
        "domains": domains,
        "repaired_actions": int(result_counts.get("repaired", 0)),
        "failed_actions": int(result_counts.get("failed", 0) + result_counts.get("blocked", 0)),
    }


def _collaboration_rollup(
    *,
    vote_summary: object,
    collaboration: object,
    strategy: object,
) -> dict[str, object]:
    vote_obj = vote_summary if isinstance(vote_summary, dict) else {}
    collab_obj = collaboration if isinstance(collaboration, dict) else {}
    transcript = collab_obj.get("transcript") if isinstance(collab_obj.get("transcript"), list) else []
    mode = str(collab_obj.get("mode") or strategy or "").strip().lower()
    decompose = mode == "decompose" or vote_obj.get("subtasks_total") is not None
    vote = mode == "vote" or vote_obj.get("winner_votes") is not None
    review_events = 0
    for item in transcript:
        if isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "subtask_review":
            review_events += 1
    return {
        "decompose": decompose,
        "vote": vote,
        "transcript_events": len(transcript),
        "review_events": review_events,
        "parallel_batches": max(0, int(vote_obj.get("parallel_batches", 0) or 0)),
        "subtasks_total": max(0, int(vote_obj.get("subtasks_total", 0) or 0)),
    }


def _build_dashboard_observability(
    *,
    jobs: list[dict[str, object]],
    plans: list[dict[str, object]],
    events: list[dict[str, object]],
    governance: dict[str, object],
) -> dict[str, object]:
    runtime_timeline: dict[str, dict[str, object]] = {}
    repair_timeline: dict[str, dict[str, object]] = {}
    collaboration_timeline: dict[str, dict[str, object]] = {}
    repair_domains: Counter[str] = Counter()
    event_categories: Counter[str] = Counter()
    failure_categories: Counter[str] = Counter()

    runtime_recent = {
        "runs": 0,
        "actions": 0,
        "estimated_cost_usd": 0.0,
        "llm_calls": 0,
        "failed_runs": 0,
        "repaired_actions": 0,
    }
    repair_summary = {
        "attempted": 0,
        "healed": 0,
        "failed": 0,
        "repaired_actions": 0,
        "failed_actions": 0,
    }
    collaboration_summary = {
        "decompose_runs": 0,
        "vote_runs": 0,
        "transcript_events": 0,
        "review_events": 0,
        "parallel_batches": 0,
        "subtasks_total": 0,
    }

    for event in events:
        if not isinstance(event, dict):
            continue
        category = str(event.get("category") or "unknown").strip().lower() or "unknown"
        status = str(event.get("status") or "").strip().lower()
        event_categories[category] += 1
        if status in {"failed", "error", "blocked"}:
            failure_categories[category] += 1

    for job in jobs:
        if not isinstance(job, dict):
            continue
        result = job.get("result") if isinstance(job.get("result"), dict) else None
        timestamp = job.get("finished_at") or job.get("started_at") or job.get("created_at")
        bucket = _timeline_bucket(timestamp)
        bucket_row = runtime_timeline.setdefault(
            bucket,
            {"runs": 0, "actions": 0, "llm_calls": 0, "estimated_cost_usd": 0.0, "failed_runs": 0, "repaired_actions": 0},
        )
        bucket_row["runs"] = int(bucket_row["runs"]) + 1
        runtime_recent["runs"] += 1
        if result is None:
            continue

        actions = result.get("actions") if isinstance(result.get("actions"), list) else []
        execution_results = result.get("results") if isinstance(result.get("results"), list) else []
        llm_calls = _usage_call_count(result.get("model_usage"))
        estimated_cost = max(0.0, float(result.get("estimated_cost_usd", 0.0) or 0.0))
        repaired_actions = sum(
            1
            for item in execution_results
            if isinstance(item, dict) and str(item.get("status") or "").strip().lower() == "repaired"
        )
        failed_run = any(
            isinstance(item, dict) and str(item.get("status") or "").strip().lower() in {"failed", "blocked"}
            for item in execution_results
        )

        bucket_row["actions"] = int(bucket_row["actions"]) + len(actions)
        bucket_row["llm_calls"] = int(bucket_row["llm_calls"]) + llm_calls
        bucket_row["estimated_cost_usd"] = round(float(bucket_row["estimated_cost_usd"]) + estimated_cost, 6)
        bucket_row["repaired_actions"] = int(bucket_row["repaired_actions"]) + repaired_actions
        if failed_run:
            bucket_row["failed_runs"] = int(bucket_row["failed_runs"]) + 1

        runtime_recent["actions"] += len(actions)
        runtime_recent["llm_calls"] += llm_calls
        runtime_recent["estimated_cost_usd"] = round(float(runtime_recent["estimated_cost_usd"]) + estimated_cost, 6)
        runtime_recent["repaired_actions"] += repaired_actions
        if failed_run:
            runtime_recent["failed_runs"] += 1

        job_kind = str(job.get("kind") or "").strip().lower()
        if job_kind in {"run", "swarm_run"}:
            repair_info = _repair_rollup(result.get("repair"), execution_results)
            if bool(repair_info["attempted"]):
                repair_bucket = repair_timeline.setdefault(
                    bucket,
                    {"attempted": 0, "healed": 0, "failed": 0, "repaired_actions": 0},
                )
                repair_summary["attempted"] += 1
                repair_bucket["attempted"] = int(repair_bucket["attempted"]) + 1
                if bool(repair_info["healed"]):
                    repair_summary["healed"] += 1
                    repair_bucket["healed"] = int(repair_bucket["healed"]) + 1
                if bool(repair_info["failed"]):
                    repair_summary["failed"] += 1
                    repair_bucket["failed"] = int(repair_bucket["failed"]) + 1
                repair_summary["repaired_actions"] += int(repair_info["repaired_actions"])
                repair_summary["failed_actions"] += int(repair_info["failed_actions"])
                repair_bucket["repaired_actions"] = int(repair_bucket["repaired_actions"]) + int(repair_info["repaired_actions"])
                repair_domains.update(repair_info["domains"])

            collab_info = _collaboration_rollup(
                vote_summary=result.get("vote_summary"),
                collaboration=result.get("collaboration"),
                strategy=result.get("strategy"),
            )
            if collab_info["decompose"] or collab_info["vote"] or int(collab_info["transcript_events"]) > 0:
                collab_bucket = collaboration_timeline.setdefault(
                    bucket,
                    {"decompose_runs": 0, "vote_runs": 0, "transcript_events": 0, "review_events": 0, "parallel_batches": 0},
                )
                if bool(collab_info["decompose"]):
                    collaboration_summary["decompose_runs"] += 1
                    collab_bucket["decompose_runs"] = int(collab_bucket["decompose_runs"]) + 1
                if bool(collab_info["vote"]):
                    collaboration_summary["vote_runs"] += 1
                    collab_bucket["vote_runs"] = int(collab_bucket["vote_runs"]) + 1
                collaboration_summary["transcript_events"] += int(collab_info["transcript_events"])
                collaboration_summary["review_events"] += int(collab_info["review_events"])
                collaboration_summary["parallel_batches"] += int(collab_info["parallel_batches"])
                collaboration_summary["subtasks_total"] += int(collab_info["subtasks_total"])
                collab_bucket["transcript_events"] = int(collab_bucket["transcript_events"]) + int(collab_info["transcript_events"])
                collab_bucket["review_events"] = int(collab_bucket["review_events"]) + int(collab_info["review_events"])
                collab_bucket["parallel_batches"] = int(collab_bucket["parallel_batches"]) + int(collab_info["parallel_batches"])

    for plan in plans:
        if not isinstance(plan, dict):
            continue
        timestamp = plan.get("executed_at") or plan.get("updated_at") or plan.get("created_at")
        bucket = _timeline_bucket(timestamp)
        repair_info = _repair_rollup(plan.get("repair"), plan.get("execution_results"))
        if bool(repair_info["attempted"]):
            repair_bucket = repair_timeline.setdefault(
                bucket,
                {"attempted": 0, "healed": 0, "failed": 0, "repaired_actions": 0},
            )
            repair_summary["attempted"] += 1
            repair_bucket["attempted"] = int(repair_bucket["attempted"]) + 1
            if bool(repair_info["healed"]):
                repair_summary["healed"] += 1
                repair_bucket["healed"] = int(repair_bucket["healed"]) + 1
            if bool(repair_info["failed"]):
                repair_summary["failed"] += 1
                repair_bucket["failed"] = int(repair_bucket["failed"]) + 1
            repair_summary["repaired_actions"] += int(repair_info["repaired_actions"])
            repair_summary["failed_actions"] += int(repair_info["failed_actions"])
            repair_bucket["repaired_actions"] = int(repair_bucket["repaired_actions"]) + int(repair_info["repaired_actions"])
            repair_domains.update(repair_info["domains"])

        collab_info = _collaboration_rollup(
            vote_summary=plan.get("vote_summary"),
            collaboration=plan.get("collaboration"),
            strategy=plan.get("strategy"),
        )
        if collab_info["decompose"] or collab_info["vote"] or int(collab_info["transcript_events"]) > 0:
            collab_bucket = collaboration_timeline.setdefault(
                bucket,
                {"decompose_runs": 0, "vote_runs": 0, "transcript_events": 0, "review_events": 0, "parallel_batches": 0},
            )
            if bool(collab_info["decompose"]):
                collaboration_summary["decompose_runs"] += 1
                collab_bucket["decompose_runs"] = int(collab_bucket["decompose_runs"]) + 1
            if bool(collab_info["vote"]):
                collaboration_summary["vote_runs"] += 1
                collab_bucket["vote_runs"] = int(collab_bucket["vote_runs"]) + 1
            collaboration_summary["transcript_events"] += int(collab_info["transcript_events"])
            collaboration_summary["review_events"] += int(collab_info["review_events"])
            collaboration_summary["parallel_batches"] += int(collab_info["parallel_batches"])
            collaboration_summary["subtasks_total"] += int(collab_info["subtasks_total"])
            collab_bucket["transcript_events"] = int(collab_bucket["transcript_events"]) + int(collab_info["transcript_events"])
            collab_bucket["review_events"] = int(collab_bucket["review_events"]) + int(collab_info["review_events"])
            collab_bucket["parallel_batches"] = int(collab_bucket["parallel_batches"]) + int(collab_info["parallel_batches"])

    per_model = governance.get("per_model") if isinstance(governance.get("per_model"), dict) else {}
    per_model_rows = []
    for name, item in per_model.items():
        if not isinstance(item, dict):
            continue
        per_model_rows.append(
            {
                "name": str(name),
                "calls": max(0, int(item.get("calls", 0) or 0)),
                "estimated_cost_usd": round(max(0.0, float(item.get("estimated_cost_usd", 0.0) or 0.0)), 6),
                "model_id": str(item.get("model_id") or ""),
            }
        )
    per_model_rows.sort(key=lambda row: (-int(row["calls"]), str(row["name"])))

    return {
        "runtime": {
            "totals": {
                "paused": bool(governance.get("paused", False)),
                "pause_reason": str(governance.get("pause_reason") or ""),
                "budget_limit_usd": governance.get("budget_limit_usd"),
                "spend_estimate_usd": round(max(0.0, float(governance.get("spend_estimate_usd", 0.0) or 0.0)), 6),
                "llm_calls_total": max(0, int(governance.get("llm_calls_total", 0) or 0)),
                "runs_total": max(0, int(governance.get("runs_total", 0) or 0)),
                "active_runs": max(0, int(governance.get("active_runs", 0) or 0)),
                "max_active_runs": governance.get("max_active_runs"),
                "last_run_at": str(governance.get("last_run_at") or ""),
                "last_strategy": str(governance.get("last_strategy") or ""),
            },
            "recent": runtime_recent,
            "per_model": per_model_rows[:8],
            "timeline": _sorted_timeline(runtime_timeline, limit=8),
        },
        "repairs": {
            **repair_summary,
            "domains": _sorted_counter(repair_domains, limit=8),
            "timeline": _sorted_timeline(repair_timeline, limit=8),
        },
        "collaboration": {
            **collaboration_summary,
            "timeline": _sorted_timeline(collaboration_timeline, limit=8),
        },
        "events": {
            "categories": _sorted_counter(event_categories, limit=8),
            "failure_categories": _sorted_counter(failure_categories, limit=8),
        },
    }


def get_health(
    handler,
    service: NovaAdaptService,
    audit_store: AuditStore | None,
    metrics,
    single,
    to_path,
    query: dict[str, list[str]],
) -> int:
    deep = (single(query, "deep") or "0") == "1"
    if not deep:
        handler._send_json(200, {"ok": True, "service": "novaadapt"})
        return 200

    include_execution_check = (single(query, "execution") or "0") == "1"
    health_payload = {
        "ok": True,
        "service": "novaadapt",
        "checks": {},
        "metrics": metrics.snapshot(),
        "capabilities": service.capabilities(),
    }
    checks = health_payload["checks"]

    config = to_path(single(query, "config"))
    try:
        checks["models"] = {"ok": True, "count": len(service.models(config_path=config))}
    except Exception as exc:
        checks["models"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["audit_store"] = {
            "ok": True,
            "recent_count": len(audit_store.list(limit=1)) if audit_store is not None else 0,
        }
    except Exception as exc:
        checks["audit_store"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["plan_store"] = {"ok": True, "recent_count": len(service.list_plans(limit=1))}
    except Exception as exc:
        checks["plan_store"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["action_log"] = {"ok": True, "recent_count": len(service.history(limit=1))}
    except Exception as exc:
        checks["action_log"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["memory"] = service.memory_status()
        if not bool(checks["memory"].get("ok", False)) and bool(checks["memory"].get("enabled", True)):
            health_payload["ok"] = False
    except Exception as exc:
        checks["memory"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    try:
        checks["novaprime"] = service.novaprime_status()
        if not bool(checks["novaprime"].get("ok", False)) and bool(checks["novaprime"].get("enabled", True)):
            health_payload["ok"] = False
    except Exception as exc:
        checks["novaprime"] = {"ok": False, "error": str(exc)}
        health_payload["ok"] = False

    if include_execution_check:
        try:
            checks["directshell"] = service.directshell_probe()
            if not bool(checks["directshell"].get("ok")):
                health_payload["ok"] = False
        except Exception as exc:
            checks["directshell"] = {"ok": False, "error": str(exc)}
            health_payload["ok"] = False

    status_code = 200 if health_payload["ok"] else 503
    handler._send_json(status_code, health_payload)
    return status_code


def get_dashboard(handler, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/dashboard", query):
        return 401
    handler._send_html(200, render_dashboard_html())
    return 200


def get_dashboard_canvas_workflows(handler, query: dict[str, list[str]]) -> int:
    if not _canvas_workflows_ui_enabled():
        handler._send_json(404, {"error": "Not found"})
        return 404
    if not handler._check_auth("/dashboard/canvas-workflows", query):
        return 401
    handler._send_html(200, render_canvas_workflows_html())
    return 200


def get_dashboard_data(
    handler,
    service: NovaAdaptService,
    job_manager,
    audit_store: AuditStore | None,
    metrics,
    single,
    to_path,
    query: dict[str, list[str]],
) -> int:
    if not handler._check_auth("/dashboard/data", query):
        return 401
    jobs_limit = int(single(query, "jobs_limit") or 25)
    plans_limit = int(single(query, "plans_limit") or 25)
    events_limit = int(single(query, "events_limit") or 25)
    control_limit = int(single(query, "control_limit") or 8)
    config = single(query, "config")
    control: dict[str, object] = {}
    try:
        control["browser"] = service.browser_status()
    except Exception as exc:
        control["browser"] = {"ok": False, "error": str(exc)}
    try:
        control["mobile"] = service.mobile_status()
    except Exception as exc:
        control["mobile"] = {"ok": False, "error": str(exc)}
    try:
        control["homeassistant"] = service.homeassistant_status()
    except Exception as exc:
        control["homeassistant"] = {"ok": False, "error": str(exc)}
    try:
        control["mqtt"] = service.mqtt_status()
    except Exception as exc:
        control["mqtt"] = {"ok": False, "error": str(exc)}
    try:
        control["artifacts"] = service.list_control_artifacts(limit=max(1, control_limit))
    except Exception as exc:
        control["artifacts"] = []
        control["artifacts_error"] = str(exc)
    job_rows = job_manager.list(limit=max(1, jobs_limit))
    job_stats = job_manager.stats()
    plans = service.list_plans(limit=max(1, plans_limit))
    events = (
        audit_store.list(limit=max(1, events_limit))
        if audit_store is not None
        else []
    )
    governance = service.runtime_governance_status(job_stats=job_stats)
    observability = _build_dashboard_observability(
        jobs=job_rows,
        plans=plans,
        events=events,
        governance=governance,
    )
    handler._send_json(
        200,
        {
            "health": {"ok": True, "service": "novaadapt"},
            "metrics": metrics.snapshot(),
            "jobs": job_rows,
            "governance": governance,
            "plans": plans,
            "events": events,
            "observability": observability,
            "models_count": len(service.models(config_path=to_path(config))),
            "control": control,
            "control_artifacts": control.get("artifacts", []),
        },
    )
    return 200


def get_openapi(handler) -> int:
    handler._send_json(200, build_openapi_spec())
    return 200


def get_metrics(handler, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/metrics", query):
        return 401
    handler._send_metrics(200)
    return 200


def get_events(handler, audit_store: AuditStore | None, single, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/events", query):
        return 401
    limit = int(single(query, "limit") or 100)
    category = single(query, "category")
    entity_type = single(query, "entity_type")
    entity_id = single(query, "entity_id")
    since_id = single(query, "since_id")
    handler._send_json(
        200,
        audit_store.list(
            limit=max(1, limit),
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            since_id=int(since_id) if since_id is not None else None,
        )
        if audit_store is not None
        else [],
    )
    return 200


def get_events_stream(handler, single, query: dict[str, list[str]]) -> int:
    if not handler._check_auth("/events/stream", query):
        return 401
    timeout_seconds = float(single(query, "timeout") or 30.0)
    interval_seconds = float(single(query, "interval") or 0.25)
    since_id = int(single(query, "since_id") or 0)
    timeout_seconds = min(300.0, max(1.0, timeout_seconds))
    interval_seconds = min(5.0, max(0.05, interval_seconds))
    handler._stream_audit_events(
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        since_id=since_id,
    )
    return 200
