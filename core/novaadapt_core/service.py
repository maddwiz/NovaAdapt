from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from novaadapt_shared import ModelRouter, UndoQueue

from .audit_store import AuditStore
from .agent import NovaAdaptAgent
from .directshell import DirectShellClient
from .plan_store import PlanStore
from .policy import ActionPolicy


class NovaAdaptService:
    """Shared application service used by CLI and HTTP server."""

    def __init__(
        self,
        default_config: Path,
        db_path: Path | None = None,
        plans_db_path: Path | None = None,
        audit_db_path: Path | None = None,
        router_loader: Callable[[Path], ModelRouter] | None = None,
        directshell_factory: Callable[[], DirectShellClient] | None = None,
    ) -> None:
        self.default_config = default_config
        self.db_path = db_path
        self.plans_db_path = plans_db_path
        self.audit_db_path = audit_db_path
        self.router_loader = router_loader or ModelRouter.from_config_file
        self.directshell_factory = directshell_factory or DirectShellClient
        self._plan_store: PlanStore | None = None
        self._audit_store: AuditStore | None = None

    def models(self, config_path: Path | None = None) -> list[dict[str, Any]]:
        router = self.router_loader(config_path or self.default_config)
        return [
            {
                "name": item.name,
                "model": item.model,
                "provider": item.provider,
                "base_url": item.base_url,
            }
            for item in router.list_models()
        ]

    def check(
        self,
        config_path: Path | None = None,
        model_names: list[str] | None = None,
        probe_prompt: str = "Reply with: OK",
    ) -> list[dict[str, object]]:
        router = self.router_loader(config_path or self.default_config)
        return router.health_check(model_names=model_names, probe_prompt=probe_prompt)

    def directshell_probe(self) -> dict[str, Any]:
        client = self.directshell_factory()
        probe_fn = getattr(client, "probe", None)
        if not callable(probe_fn):
            return {
                "ok": False,
                "error": "DirectShell probe is not implemented by current directshell_factory",
            }
        result = probe_fn()
        if isinstance(result, dict):
            return result
        return {
            "ok": False,
            "error": "DirectShell probe returned invalid payload",
        }

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        config_path = Path(payload.get("config") or self.default_config)
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("'objective' is required")

        strategy = str(payload.get("strategy", "single"))
        model_name = payload.get("model")
        candidate_models = self._as_name_list(payload.get("candidates"))
        fallback_models = self._as_name_list(payload.get("fallbacks"))
        execute = bool(payload.get("execute", False))
        record_history = bool(payload.get("record_history", True))
        allow_dangerous = bool(payload.get("allow_dangerous", False))
        max_actions = int(payload.get("max_actions", 25))

        router = self.router_loader(config_path)
        queue = UndoQueue(db_path=self.db_path)
        agent = NovaAdaptAgent(
            router=router,
            directshell=self.directshell_factory(),
            undo_queue=queue,
        )
        return agent.run_objective(
            objective=objective,
            strategy=strategy,
            model_name=model_name,
            candidate_models=candidate_models or None,
            fallback_models=fallback_models or None,
            dry_run=not execute,
            record_history=record_history,
            allow_dangerous=allow_dangerous,
            max_actions=max(1, max_actions),
        )

    def create_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        plan_preview = self.run(
            {
                **payload,
                "execute": False,
                "record_history": False,
            }
        )
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            raise ValueError("'objective' is required")
        stored = self._plans().create(
            {
                "objective": objective,
                "strategy": str(payload.get("strategy", "single")),
                "model": plan_preview.get("model"),
                "model_id": plan_preview.get("model_id"),
                "actions": plan_preview.get("actions", []),
                "votes": plan_preview.get("votes", {}),
                "model_errors": plan_preview.get("model_errors", {}),
                "attempted_models": plan_preview.get("attempted_models", []),
                "status": "pending",
            }
        )
        stored["preview_results"] = plan_preview.get("results", [])
        return stored

    def list_plans(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._plans().list(limit=max(1, int(limit)))

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._plans().get(plan_id)

    def approve_plan(self, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self._plans().get(plan_id)
        if plan is None:
            raise ValueError("Plan not found")
        if plan["status"] == "rejected":
            raise ValueError("Plan already rejected")
        if plan["status"] == "executing":
            raise ValueError("Plan is already executing")
        if plan["status"] == "executed":
            return plan

        execute = bool(payload.get("execute", True))
        allow_dangerous = bool(payload.get("allow_dangerous", False))
        max_actions = int(payload.get("max_actions", len(plan.get("actions", [])) or 1))
        action_retry_attempts = max(0, int(payload.get("action_retry_attempts", 0)))
        action_retry_backoff_seconds = max(0.0, float(payload.get("action_retry_backoff_seconds", 0.25)))

        if not execute:
            approved = self._plans().approve(plan_id=plan_id, status="approved")
            if approved is None:
                raise ValueError("Plan not found")
            return approved

        actions = [item for item in plan.get("actions", []) if isinstance(item, dict)]
        actions = actions[: max(1, max_actions)]
        policy = ActionPolicy()
        queue = UndoQueue(db_path=self.db_path)
        directshell = self.directshell_factory()
        self._plans().mark_executing(plan_id=plan_id, total_actions=len(actions))

        execution_results: list[dict[str, Any]] = []
        action_log_ids: list[int] = []
        try:
            for idx, action in enumerate(actions, start=1):
                decision = policy.evaluate(action, allow_dangerous=allow_dangerous)
                undo_action = action.get("undo") if isinstance(action.get("undo"), dict) else None
                if not decision.allowed:
                    execution_results.append(
                        {
                            "status": "blocked",
                            "output": decision.reason,
                            "action": action,
                            "dangerous": decision.dangerous,
                        }
                    )
                    action_log_ids.append(
                        queue.record(
                            action=action,
                            status="blocked",
                            undo_action=undo_action,
                        )
                    )
                    self._plans().update_execution_progress(
                        plan_id=plan_id,
                        execution_results=execution_results,
                        action_log_ids=action_log_ids,
                        progress_completed=idx,
                        progress_total=len(actions),
                    )
                    continue

                run_result = directshell.execute_action(action=action, dry_run=False)
                attempts = 1
                while str(run_result.status).lower() != "ok" and attempts <= action_retry_attempts:
                    if action_retry_backoff_seconds > 0:
                        time.sleep(action_retry_backoff_seconds * (2 ** (attempts - 1)))
                    run_result = directshell.execute_action(action=action, dry_run=False)
                    attempts += 1
                execution_results.append(
                    {
                        "status": run_result.status,
                        "output": run_result.output,
                        "action": run_result.action,
                        "dangerous": decision.dangerous,
                        "attempts": attempts,
                    }
                )
                action_log_ids.append(
                    queue.record(
                        action=run_result.action,
                        status=run_result.status,
                        undo_action=undo_action,
                    )
                )
                self._plans().update_execution_progress(
                    plan_id=plan_id,
                    execution_results=execution_results,
                    action_log_ids=action_log_ids,
                    progress_completed=idx,
                    progress_total=len(actions),
                )
        except Exception as exc:  # pragma: no cover - defensive execution boundary
            self._plans().fail_execution(
                plan_id=plan_id,
                error=str(exc),
                execution_results=execution_results,
                action_log_ids=action_log_ids,
                progress_completed=len(execution_results),
                progress_total=len(actions),
            )
            raise

        failed_actions = [
            item
            for item in execution_results
            if str(item.get("status", "")).lower() in {"failed", "blocked"}
        ]
        if failed_actions:
            failed = self._plans().fail_execution(
                plan_id=plan_id,
                error=f"{len(failed_actions)} actions failed or were blocked",
                execution_results=execution_results,
                action_log_ids=action_log_ids,
                progress_completed=len(execution_results),
                progress_total=len(actions),
            )
            if failed is None:
                raise ValueError("Plan not found")
            return failed

        approved = self._plans().approve(
            plan_id=plan_id,
            execution_results=execution_results,
            action_log_ids=action_log_ids,
            status="executed",
        )
        if approved is None:
            raise ValueError("Plan not found")
        return approved

    def reject_plan(self, plan_id: str, reason: str | None = None) -> dict[str, Any]:
        plan = self._plans().get(plan_id)
        if plan is None:
            raise ValueError("Plan not found")
        if plan["status"] == "executed":
            raise ValueError("Plan already executed")
        rejected = self._plans().reject(plan_id, reason=reason)
        if rejected is None:
            raise ValueError("Plan not found")
        return rejected

    def undo_plan(self, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = self._plans().get(plan_id)
        if plan is None:
            raise ValueError("Plan not found")
        action_log_ids = plan.get("action_log_ids") or []
        if not isinstance(action_log_ids, list) or not action_log_ids:
            raise ValueError("Plan has no recorded action logs to undo")

        execute = bool(payload.get("execute", False))
        mark_only = bool(payload.get("mark_only", False))
        results: list[dict[str, Any]] = []
        for action_id in reversed(action_log_ids):
            try:
                result = self.undo(
                    {
                        "id": int(action_id),
                        "execute": execute,
                        "mark_only": mark_only,
                    }
                )
                results.append({"id": int(action_id), "ok": True, "result": result})
            except ValueError as exc:
                results.append({"id": int(action_id), "ok": False, "error": str(exc)})

        return {
            "plan_id": plan_id,
            "executed": execute,
            "mark_only": mark_only,
            "results": results,
        }

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        queue = UndoQueue(db_path=self.db_path)
        return queue.recent(limit=max(1, int(limit)))

    def undo(self, payload: dict[str, Any]) -> dict[str, Any]:
        queue = UndoQueue(db_path=self.db_path)
        action_id = payload.get("id")
        mark_only = bool(payload.get("mark_only", False))
        execute = bool(payload.get("execute", False))

        item = queue.get(int(action_id)) if action_id is not None else queue.latest_pending()
        if item is None:
            raise ValueError("No matching action found in log")

        if item["undone"]:
            raise ValueError(f"Action {item['id']} is already marked undone")

        undo_action = item.get("undo_action")
        if undo_action is None and not mark_only:
            raise ValueError(
                "No undo action stored for this record. Set 'mark_only': true to mark it manually."
            )

        if mark_only:
            queue.mark_undone(item["id"])
            return {"id": item["id"], "status": "marked_undone", "mode": "mark_only"}

        directshell = self.directshell_factory()
        result = directshell.execute_action(action=undo_action, dry_run=not execute)
        marked = bool(execute and result.status == "ok")
        if marked:
            queue.mark_undone(item["id"])
        return {
            "id": item["id"],
            "executed": execute,
            "undo_result": {
                "status": result.status,
                "output": result.output,
                "action": result.action,
            },
            "marked_undone": marked,
        }

    def events(
        self,
        limit: int = 100,
        category: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._audits().list(
            limit=max(1, int(limit)),
            category=category,
            entity_type=entity_type,
            entity_id=entity_id,
            since_id=(int(since_id) if since_id is not None else None),
        )

    def events_wait(
        self,
        *,
        timeout_seconds: float = 30.0,
        interval_seconds: float = 0.25,
        limit: int = 100,
        category: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since_id: int | None = None,
    ) -> list[dict[str, Any]]:
        timeout = min(300.0, max(0.1, float(timeout_seconds)))
        interval = min(5.0, max(0.01, float(interval_seconds)))
        deadline = time.monotonic() + timeout
        marker = int(since_id) if since_id is not None else None

        while True:
            rows = self.events(
                limit=max(1, int(limit)),
                category=category,
                entity_type=entity_type,
                entity_id=entity_id,
                since_id=marker,
            )
            if rows:
                # events() returns descending; watchers generally want oldest-first.
                return list(reversed(rows))
            if time.monotonic() >= deadline:
                return []
            time.sleep(interval)

    @staticmethod
    def _as_name_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    def _plans(self) -> PlanStore:
        if self._plan_store is None:
            self._plan_store = PlanStore(self.plans_db_path)
        return self._plan_store

    def _audits(self) -> AuditStore:
        if self._audit_store is None:
            self._audit_store = AuditStore(self.audit_db_path)
        return self._audit_store
