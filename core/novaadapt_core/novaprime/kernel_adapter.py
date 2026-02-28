from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from typing import Any

from ..agent import NovaAdaptAgent


def _flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def should_use_kernel(payload: dict[str, Any] | None = None) -> bool:
    row = payload if isinstance(payload, dict) else {}
    if "use_kernel" in row:
        return _flag(row.get("use_kernel"), False)
    return _flag(os.getenv("NOVAADAPT_USE_NOVAPRIME_KERNEL"), False)


def kernel_required(payload: dict[str, Any] | None = None) -> bool:
    row = payload if isinstance(payload, dict) else {}
    if "kernel_required" in row:
        return _flag(row.get("kernel_required"), False)
    return _flag(os.getenv("NOVAADAPT_KERNEL_REQUIRED"), False)


def _resolve_kernel_symbols() -> tuple[Any, Any, Any, Any]:
    from novaprime.kernel.entrypoint import run_agent_job
    from novaprime.kernel.policy_profile import resolve_policy_profile
    from novaprime.kernel.schemas import AgentJob, IdentityContext

    return run_agent_job, resolve_policy_profile, AgentJob, IdentityContext


class _KernelMemoryBridge:
    def __init__(self, backend: Any) -> None:
        self.backend = backend

    def augment(self, query: str, top_k: int = 3, *, fmt: str = "plain") -> dict[str, Any]:
        out = ""
        if hasattr(self.backend, "augment"):
            try:
                out = self.backend.augment(
                    query=str(query or ""),
                    top_k=max(1, int(top_k)),
                    min_score=0.0,
                    format_name="plain" if str(fmt).strip().lower() == "plain" else "xml",
                )
            except Exception:
                out = ""
        return {"context": str(out or "")}

    def store(self, key: str, data: Any, metadata: dict[str, Any] | None = None) -> None:
        if not hasattr(self.backend, "ingest"):
            return
        meta = dict(metadata or {})
        meta.setdefault("source", "novaprime_kernel")
        meta.setdefault("kernel_key", str(key))
        source_id = f"novaprime-kernel:{str(key)}:{int(time.time() * 1000)}"
        body = json.dumps({"key": str(key), "data": data}, ensure_ascii=True, default=str)
        try:
            self.backend.ingest(body, source_id=source_id, metadata=meta)
        except Exception:
            return


def _resolve_identity_context(
    *,
    identity_cls: Any,
    adapt_id: str,
    player_id: str,
    identity_profile: dict[str, Any] | None,
) -> Any:
    profile = identity_profile if isinstance(identity_profile, dict) else {}
    return identity_cls(
        adapt_id=str(adapt_id or ""),
        player_id=str(player_id or ""),
        element=str(profile.get("element", "") or ""),
        subclass=str(profile.get("subclass", "") or ""),
        bond_strength=float(profile.get("bond_strength", 0.0) or 0.0),
        form_stage=str(profile.get("form_stage", "") or ""),
        realm=str(profile.get("realm", "") or ""),
        extra={"identity_profile": profile},
    )


def run_with_kernel(
    *,
    payload: dict[str, Any],
    objective: str,
    strategy: str,
    model_name: str | None,
    router: Any,
    agent: NovaAdaptAgent,
    execute: bool,
    record_history: bool,
    allow_dangerous: bool,
    max_actions: int,
    adapt_id: str,
    player_id: str,
    identity_profile: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        run_agent_job, resolve_policy_profile, agent_job_cls, identity_ctx_cls = _resolve_kernel_symbols()
    except Exception as exc:
        return {
            "ok": False,
            "error": f"novaprime kernel unavailable: {exc}",
            "kernel": {"ok": False, "error": f"novaprime kernel unavailable: {exc}"},
        }

    profile_name = str(
        payload.get("profile_name")
        or payload.get("policy_profile")
        or os.getenv("NOVAADAPT_KERNEL_PROFILE", "unleashed_local")
    ).strip() or "unleashed_local"

    try:
        profile = resolve_policy_profile(profile_name)
    except Exception:
        profile = profile_name
    else:
        if model_name and hasattr(profile, "architect_model"):
            try:
                profile = replace(profile, architect_model=str(model_name), oracle_model=str(model_name))
            except Exception:
                pass

    job_data: dict[str, Any] = {
        "input_text": str(objective or ""),
        "job_id": str(payload.get("job_id") or ""),
        "session_id": str(payload.get("session_id") or ""),
        "source": str(payload.get("source") or "novaadapt"),
        "workspace_id": str(payload.get("workspace_id") or "default"),
        "profile_name": profile_name,
        "reply_to": payload.get("reply_to") if isinstance(payload.get("reply_to"), dict) else {},
        "attachments": payload.get("attachments") if isinstance(payload.get("attachments"), list) else [],
        "parent_job_id": str(payload.get("parent_job_id") or ""),
        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
    }
    job = agent_job_cls.from_dict(job_data)
    identity_ctx = _resolve_identity_context(
        identity_cls=identity_ctx_cls,
        adapt_id=adapt_id,
        player_id=player_id,
        identity_profile=identity_profile,
    )

    kernel_memory = _KernelMemoryBridge(getattr(agent, "memory_backend", None))
    try:
        kernel_result = run_agent_job(
            job,
            router=router,
            profile=profile,
            memory=kernel_memory,
            identity_ctx=identity_ctx,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error": f"novaprime kernel execution failed: {exc}",
            "kernel": {"ok": False, "error": f"novaprime kernel execution failed: {exc}", "profile_name": profile_name},
        }

    output_text = str(getattr(kernel_result, "output_text", "") or "")
    kernel_ok = bool(getattr(kernel_result, "ok", False))
    kernel_error = str(getattr(kernel_result, "error", "") or "")
    actions = NovaAdaptAgent._parse_actions(output_text, max_actions=max(1, int(max_actions)))

    dry_run = not bool(execute)
    execution: list[dict[str, Any]] = []
    action_log_ids: list[int] = []
    for action in actions:
        decision = agent.policy.evaluate(action, allow_dangerous=bool(allow_dangerous))
        undo_action = action.get("undo") if isinstance(action.get("undo"), dict) else None
        if not dry_run and not decision.allowed:
            blocked_payload = {
                "status": "blocked",
                "output": decision.reason,
                "action": action,
                "dangerous": decision.dangerous,
            }
            execution.append(blocked_payload)
            if bool(record_history):
                action_log_ids.append(
                    agent.undo_queue.record(
                        action=action,
                        status="blocked",
                        undo_action=undo_action,
                    )
                )
            continue

        run_result = agent.directshell.execute_action(action=action, dry_run=dry_run)
        execution.append(
            {
                "status": run_result.status,
                "output": run_result.output,
                "action": run_result.action,
                "dangerous": decision.dangerous,
            }
        )
        if bool(record_history):
            action_log_ids.append(
                agent.undo_queue.record(
                    action=run_result.action,
                    status=run_result.status,
                    undo_action=undo_action,
                )
            )

    model_errors: dict[str, Any] = {}
    if not kernel_ok:
        model_errors["kernel"] = kernel_error or "kernel returned unsuccessful result"
    result_payload: dict[str, Any] = {
        "model": str(model_name or "novaprime-kernel"),
        "model_id": "novaprime-kernel",
        "strategy": f"kernel:{strategy}",
        "votes": {},
        "vote_summary": "",
        "model_errors": model_errors,
        "attempted_models": [str(model_name or "novaprime-kernel")],
        "actions": actions,
        "results": execution,
        "action_log_ids": action_log_ids,
        "kernel_output_text": output_text,
    }

    try:
        agent._persist_run_memory(
            objective=str(objective or ""),
            strategy=f"kernel:{strategy}",
            model=str(model_name or "novaprime-kernel"),
            model_id="novaprime-kernel",
            dry_run=dry_run,
            actions=actions,
            execution=execution,
        )
    except Exception:
        pass

    kernel_payload = {
        "ok": kernel_ok,
        "profile_name": profile_name,
        "job_id": str(getattr(kernel_result, "job_id", "") or ""),
        "session_id": str(getattr(kernel_result, "session_id", "") or ""),
    }
    if kernel_error:
        kernel_payload["error"] = kernel_error
    artifacts = getattr(kernel_result, "artifacts", None)
    if isinstance(artifacts, list):
        kernel_payload["artifacts"] = artifacts

    return {
        "ok": kernel_ok,
        "error": kernel_error,
        "result": result_payload,
        "kernel": kernel_payload,
    }
