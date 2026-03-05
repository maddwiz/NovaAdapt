from __future__ import annotations

from typing import Any

from .checkpoints import WorkflowCheckpointStore
from .store import WorkflowRecord, WorkflowStore


class WorkflowEngine:
    """Minimal workflow runner with persistent state and checkpoints."""

    def __init__(
        self,
        store: WorkflowStore,
        *,
        checkpoints: WorkflowCheckpointStore | None = None,
    ) -> None:
        self.store = store
        self.checkpoints = checkpoints

    def start(
        self,
        objective: str,
        *,
        steps: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
        workflow_id: str = "",
    ) -> WorkflowRecord:
        normalized_steps = [dict(step) for step in (steps or [])]
        normalized_context = dict(context or {})
        normalized_context.setdefault("current_step", 0)
        record = self.store.create(
            objective,
            steps=normalized_steps,
            context=normalized_context,
            workflow_id=workflow_id,
            status="queued",
        )
        self._checkpoint(record.workflow_id, "start", {"status": "queued", "context": normalized_context})
        return record

    def advance(
        self,
        workflow_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> WorkflowRecord | None:
        current = self.store.get(workflow_id)
        if current is None:
            return None
        if current.status in {"done", "failed"}:
            return current

        steps = [dict(step) for step in current.steps]
        context = dict(current.context or {})
        idx = int(context.get("current_step", 0))
        max_idx = len(steps)

        if error:
            updated = self.store.update(
                current.workflow_id,
                status="failed",
                steps=steps,
                context=context,
                last_error=str(error),
            )
            if updated is not None:
                self._checkpoint(updated.workflow_id, f"step-{idx}-failed", {"error": str(error)})
            return updated

        if max_idx == 0:
            updated = self.store.update(current.workflow_id, status="done", steps=steps, context=context)
            if updated is not None:
                self._checkpoint(updated.workflow_id, "done", {"status": "done", "empty_steps": True})
            return updated

        if idx < max_idx:
            step = dict(steps[idx])
            step["status"] = "done"
            if isinstance(result, dict):
                step["result"] = dict(result)
            steps[idx] = step
            idx += 1
            context["current_step"] = idx

        next_status = "done" if idx >= max_idx else "running"
        updated = self.store.update(
            current.workflow_id,
            status=next_status,
            steps=steps,
            context=context,
            last_error="" if next_status != "failed" else current.last_error,
        )
        if updated is not None:
            self._checkpoint(
                updated.workflow_id,
                f"step-{idx}",
                {"status": next_status, "current_step": idx, "result": dict(result or {})},
            )
        return updated

    def resume(self, workflow_id: str) -> WorkflowRecord | None:
        current = self.store.get(workflow_id)
        if current is None:
            return None
        if current.status in {"done", "running"}:
            return current
        updated = self.store.update(current.workflow_id, status="running", last_error="")
        if updated is not None:
            self._checkpoint(updated.workflow_id, "resume", {"status": "running"})
        return updated

    def _checkpoint(self, workflow_id: str, checkpoint_id: str, payload: dict[str, Any]) -> None:
        if self.checkpoints is None:
            return
        self.checkpoints.save(workflow_id, checkpoint_id, payload)
