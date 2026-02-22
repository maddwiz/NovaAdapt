from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from novaadapt_shared import ModelRouter, UndoQueue

from .agent import NovaAdaptAgent
from .directshell import DirectShellClient


class NovaAdaptService:
    """Shared application service used by CLI and HTTP server."""

    def __init__(
        self,
        default_config: Path,
        db_path: Path | None = None,
        router_loader: Callable[[Path], ModelRouter] | None = None,
        directshell_factory: Callable[[], DirectShellClient] | None = None,
    ) -> None:
        self.default_config = default_config
        self.db_path = db_path
        self.router_loader = router_loader or ModelRouter.from_config_file
        self.directshell_factory = directshell_factory or DirectShellClient

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
            allow_dangerous=allow_dangerous,
            max_actions=max(1, max_actions),
        )

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

    @staticmethod
    def _as_name_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []
