from __future__ import annotations

import json
from typing import Any

from novaadapt_shared import ModelRouter, UndoQueue

from .directshell import DirectShellClient


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
    ) -> None:
        self.router = router
        self.directshell = directshell or DirectShellClient()
        self.undo_queue = undo_queue or UndoQueue()

    def run_objective(
        self,
        objective: str,
        strategy: str = "single",
        model_name: str | None = None,
        candidate_models: list[str] | None = None,
        dry_run: bool = True,
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
        )

        actions = self._parse_actions(result.content)
        execution = self.directshell.run_plan(actions, dry_run=dry_run)

        action_log_ids: list[int] = []
        for item in execution:
            action_log_ids.append(self.undo_queue.record(action=item.action, status=item.status))

        return {
            "model": result.model_name,
            "model_id": result.model_id,
            "strategy": result.strategy,
            "votes": result.votes,
            "actions": actions,
            "results": [
                {
                    "status": item.status,
                    "output": item.output,
                    "action": item.action,
                }
                for item in execution
            ],
            "action_log_ids": action_log_ids,
        }

    @staticmethod
    def _parse_actions(raw: str) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [{"type": "note", "target": "model_output", "value": raw[:500]}]

        if isinstance(parsed, dict) and isinstance(parsed.get("actions"), list):
            actions = [item for item in parsed["actions"] if isinstance(item, dict)]
            if actions:
                return actions

        if isinstance(parsed, list):
            actions = [item for item in parsed if isinstance(item, dict)]
            if actions:
                return actions

        return [{"type": "note", "target": "empty_plan", "value": "Model did not return actions"}]
