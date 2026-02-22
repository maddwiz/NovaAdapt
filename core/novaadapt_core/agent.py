from __future__ import annotations

import json
from typing import Any

from novaadapt_shared import ModelRouter, UndoQueue

from .directshell import DirectShellClient
from .policy import ActionPolicy


SYSTEM_PROMPT = (
    "You are NovaAdapt. Convert the objective into deterministic desktop actions. "
    "Return strict JSON only. Use schema: {\"actions\": [ {\"type\": str, \"target\": str, \"value\": str?} ] }."
)


class NovaAdaptAgent:
    def __init__(
        self,
        router: ModelRouter,
        directshell: DirectShellClient | None = None,
        undo_queue: UndoQueue | None = None,
        policy: ActionPolicy | None = None,
    ) -> None:
        self.router = router
        self.directshell = directshell or DirectShellClient()
        self.undo_queue = undo_queue or UndoQueue()
        self.policy = policy or ActionPolicy()

    def run_objective(
        self,
        objective: str,
        strategy: str = "single",
        model_name: str | None = None,
        candidate_models: list[str] | None = None,
        fallback_models: list[str] | None = None,
        dry_run: bool = True,
        allow_dangerous: bool = False,
        max_actions: int = 25,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Objective:\n"
                    f"{objective}\n\n"
                    "Only output JSON matching the schema, with no markdown."
                ),
            },
        ]

        result = self.router.chat(
            messages=messages,
            model_name=model_name,
            strategy=strategy,
            candidate_models=candidate_models,
            fallback_models=fallback_models,
        )

        actions = self._parse_actions(result.content, max_actions=max_actions)

        execution: list[dict[str, Any]] = []
        action_log_ids: list[int] = []
        for action in actions:
            decision = self.policy.evaluate(action, allow_dangerous=allow_dangerous)
            undo_action = action.get("undo") if isinstance(action.get("undo"), dict) else None
            if not dry_run and not decision.allowed:
                blocked_payload = {
                    "status": "blocked",
                    "output": decision.reason,
                    "action": action,
                    "dangerous": decision.dangerous,
                }
                execution.append(blocked_payload)
                action_log_ids.append(
                    self.undo_queue.record(
                        action=action,
                        status="blocked",
                        undo_action=undo_action,
                    )
                )
                continue

            run_result = self.directshell.execute_action(action=action, dry_run=dry_run)
            execution.append(
                {
                    "status": run_result.status,
                    "output": run_result.output,
                    "action": run_result.action,
                    "dangerous": decision.dangerous,
                }
            )
            action_log_ids.append(
                self.undo_queue.record(
                    action=run_result.action,
                    status=run_result.status,
                    undo_action=undo_action,
                )
            )

        return {
            "model": result.model_name,
            "model_id": result.model_id,
            "strategy": result.strategy,
            "votes": result.votes,
            "model_errors": result.errors,
            "attempted_models": result.attempted_models,
            "actions": actions,
            "results": execution,
            "action_log_ids": action_log_ids,
        }

    @staticmethod
    def _parse_actions(raw: str, max_actions: int = 25) -> list[dict[str, Any]]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            stripped = stripped.replace("json\n", "", 1).strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [{"type": "note", "target": "model_output", "value": raw[:500]}]

        if isinstance(parsed, dict) and isinstance(parsed.get("actions"), list):
            actions = [item for item in parsed["actions"] if isinstance(item, dict)]
            if actions:
                return NovaAdaptAgent._sanitize_actions(actions[:max_actions])

        if isinstance(parsed, list):
            actions = [item for item in parsed if isinstance(item, dict)]
            if actions:
                return NovaAdaptAgent._sanitize_actions(actions[:max_actions])

        return [{"type": "note", "target": "empty_plan", "value": "Model did not return actions"}]

    @staticmethod
    def _sanitize_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clean: list[dict[str, Any]] = []
        for idx, action in enumerate(actions):
            action_type = str(action.get("type", "")).strip()
            target = str(action.get("target", "")).strip()
            value = action.get("value")
            undo = action.get("undo")

            if not action_type or not target:
                clean.append(
                    {
                        "type": "note",
                        "target": "invalid_action",
                        "value": f"Action {idx} missing required fields",
                    }
                )
                continue

            normalized: dict[str, Any] = {"type": action_type, "target": target}
            if value is not None:
                normalized["value"] = str(value)
            if isinstance(undo, dict):
                normalized["undo"] = undo
            clean.append(normalized)
        return clean
