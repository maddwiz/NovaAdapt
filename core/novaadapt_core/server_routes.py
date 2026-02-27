from __future__ import annotations

from typing import Any


def build_get_public_routes(handler: Any) -> dict[str, Any]:
    return {
        "/health": handler._get_health,
        "/dashboard": handler._get_dashboard,
        "/dashboard/data": handler._get_dashboard_data,
        "/openapi.json": handler._get_openapi,
        "/metrics": handler._get_metrics,
        "/events": handler._get_events,
        "/events/stream": handler._get_events_stream,
    }


def build_get_private_routes(handler: Any) -> dict[str, Any]:
    return {
        "/models": handler._get_models,
        "/history": handler._get_history,
        "/jobs": handler._get_jobs,
        "/plans": handler._get_plans,
        "/plugins": handler._get_plugins,
        "/memory/status": handler._get_memory_status,
        "/novaprime/status": handler._get_novaprime_status,
        "/novaprime/reason/emotion": handler._get_novaprime_emotion,
        "/novaprime/mesh/balance": handler._get_novaprime_mesh_balance,
        "/novaprime/marketplace/listings": handler._get_novaprime_marketplace_listings,
        "/novaprime/identity/profile": handler._get_novaprime_identity_profile,
        "/novaprime/presence": handler._get_novaprime_presence,
        "/sib/status": handler._get_sib_status,
        "/adapt/toggle": handler._get_adapt_toggle,
        "/adapt/bond": handler._get_adapt_bond,
        "/terminal/sessions": handler._get_terminal_sessions,
        "/browser/status": handler._get_browser_status,
        "/browser/pages": handler._get_browser_pages,
    }


def build_get_dynamic_routes(handler: Any) -> tuple[tuple[str, str, Any], ...]:
    return (
        ("/jobs/", "/stream", handler._get_job_stream),
        ("/jobs/", "", handler._get_job_item),
        ("/plans/", "/stream", handler._get_plan_stream),
        ("/plans/", "", handler._get_plan_item),
        ("/plugins/", "/health", handler._get_plugin_health),
        ("/terminal/sessions/", "/output", handler._get_terminal_output),
        ("/terminal/sessions/", "", handler._get_terminal_session_item),
    )


def build_post_exact_routes(handler: Any) -> dict[str, Any]:
    return {
        "/plans": lambda body: handler._post_create_plan("/plans", body),
        "/run": lambda body: handler._post_run("/run", body),
        "/run_async": lambda body: handler._post_run_async("/run_async", body),
        "/swarm/run": lambda body: handler._post_swarm_run("/swarm/run", body),
        "/undo": lambda body: handler._post_undo("/undo", body),
        "/check": handler._post_check,
        "/feedback": lambda body: handler._post_feedback("/feedback", body),
        "/sib/realm": lambda body: handler._post_sib_realm("/sib/realm", body),
        "/sib/companion/state": lambda body: handler._post_sib_companion_state("/sib/companion/state", body),
        "/sib/companion/speak": lambda body: handler._post_sib_companion_speak("/sib/companion/speak", body),
        "/sib/phase-event": lambda body: handler._post_sib_phase_event("/sib/phase-event", body),
        "/sib/resonance/start": lambda body: handler._post_sib_resonance_start("/sib/resonance/start", body),
        "/sib/resonance/result": lambda body: handler._post_sib_resonance_result("/sib/resonance/result", body),
        "/novaprime/reason/dual": lambda body: handler._post_novaprime_reason_dual("/novaprime/reason/dual", body),
        "/novaprime/reason/emotion": lambda body: handler._post_novaprime_emotion("/novaprime/reason/emotion", body),
        "/novaprime/mesh/credit": lambda body: handler._post_novaprime_mesh_credit("/novaprime/mesh/credit", body),
        "/novaprime/mesh/transfer": lambda body: handler._post_novaprime_mesh_transfer(
            "/novaprime/mesh/transfer", body
        ),
        "/novaprime/marketplace/list": lambda body: handler._post_novaprime_marketplace_list(
            "/novaprime/marketplace/list", body
        ),
        "/novaprime/marketplace/buy": lambda body: handler._post_novaprime_marketplace_buy(
            "/novaprime/marketplace/buy", body
        ),
        "/novaprime/identity/bond": lambda body: handler._post_novaprime_identity_bond(
            "/novaprime/identity/bond", body
        ),
        "/novaprime/identity/verify": lambda body: handler._post_novaprime_identity_verify(
            "/novaprime/identity/verify", body
        ),
        "/novaprime/identity/evolve": lambda body: handler._post_novaprime_identity_evolve(
            "/novaprime/identity/evolve", body
        ),
        "/novaprime/presence/update": lambda body: handler._post_novaprime_presence_update(
            "/novaprime/presence/update", body
        ),
        "/novaprime/resonance/score": lambda body: handler._post_novaprime_resonance_score(
            "/novaprime/resonance/score", body
        ),
        "/novaprime/resonance/bond": lambda body: handler._post_novaprime_resonance_bond(
            "/novaprime/resonance/bond", body
        ),
        "/adapt/toggle": lambda body: handler._post_adapt_toggle("/adapt/toggle", body),
        "/memory/recall": lambda body: handler._post_memory_recall("/memory/recall", body),
        "/memory/ingest": lambda body: handler._post_memory_ingest("/memory/ingest", body),
        "/terminal/sessions": lambda body: handler._post_terminal_start("/terminal/sessions", body),
        "/browser/action": lambda body: handler._post_browser_action("/browser/action", body),
        "/browser/navigate": lambda body: handler._post_browser_navigate("/browser/navigate", body),
        "/browser/click": lambda body: handler._post_browser_click("/browser/click", body),
        "/browser/fill": lambda body: handler._post_browser_fill("/browser/fill", body),
        "/browser/extract_text": lambda body: handler._post_browser_extract_text("/browser/extract_text", body),
        "/browser/screenshot": lambda body: handler._post_browser_screenshot("/browser/screenshot", body),
        "/browser/wait_for_selector": lambda body: handler._post_browser_wait_for_selector(
            "/browser/wait_for_selector", body
        ),
        "/browser/evaluate_js": lambda body: handler._post_browser_evaluate_js("/browser/evaluate_js", body),
        "/browser/close": lambda body: handler._post_browser_close("/browser/close", body),
    }


def build_post_dynamic_routes(handler: Any) -> tuple[tuple[str, str, Any], ...]:
    return (
        ("/jobs/", "/cancel", handler._post_cancel_job),
        ("/plugins/", "/call", handler._post_plugin_call),
        ("/terminal/sessions/", "/input", handler._post_terminal_input),
        ("/terminal/sessions/", "/close", handler._post_terminal_close),
        ("/plans/", "/approve_async", handler._post_plan_approve_async),
        ("/plans/", "/retry_failed_async", handler._post_plan_retry_failed_async),
        ("/plans/", "/retry_failed", handler._post_plan_retry_failed),
        ("/plans/", "/approve", handler._post_plan_approve),
        ("/plans/", "/reject", handler._post_plan_reject),
        ("/plans/", "/undo", handler._post_plan_undo),
    )


def is_idempotent_route(path: str) -> bool:
    if path in {"/run", "/run_async", "/swarm/run", "/undo", "/plans"}:
        return True
    if path in {"/feedback"}:
        return True
    if path in {
        "/sib/realm",
        "/sib/companion/state",
        "/sib/companion/speak",
        "/sib/phase-event",
        "/sib/resonance/start",
        "/sib/resonance/result",
        "/novaprime/identity/bond",
        "/novaprime/identity/verify",
        "/novaprime/identity/evolve",
        "/novaprime/presence/update",
        "/novaprime/resonance/score",
        "/novaprime/resonance/bond",
        "/novaprime/reason/dual",
        "/novaprime/reason/emotion",
        "/novaprime/mesh/credit",
        "/novaprime/mesh/transfer",
        "/novaprime/marketplace/list",
        "/novaprime/marketplace/buy",
    }:
        return True
    if path in {"/adapt/toggle"}:
        return True
    if path in {"/memory/ingest"}:
        return True
    if path in {"/terminal/sessions"}:
        return True
    if path.startswith("/jobs/") and path.endswith("/cancel"):
        return True
    if path.startswith("/plugins/") and path.endswith("/call"):
        return True
    if path.startswith("/browser/"):
        return True
    if path.startswith("/terminal/sessions/") and path.endswith("/close"):
        return True
    if path.startswith("/plans/") and (
        path.endswith("/approve")
        or path.endswith("/approve_async")
        or path.endswith("/retry_failed_async")
        or path.endswith("/retry_failed")
        or path.endswith("/reject")
        or path.endswith("/undo")
    ):
        return True
    return False
