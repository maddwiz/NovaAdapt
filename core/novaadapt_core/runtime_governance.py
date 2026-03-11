from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_UNSET = object()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeGovernance:
    def __init__(self, state_path: Path | None = None) -> None:
        self.state_path = Path(state_path) if state_path is not None else None
        self._condition = threading.Condition()
        self._active_runs = 0
        self._state: dict[str, Any] = {
            "paused": False,
            "pause_reason": "",
            "budget_limit_usd": None,
            "spend_estimate_usd": 0.0,
            "llm_calls_total": 0,
            "runs_total": 0,
            "max_active_runs": None,
            "per_model": {},
            "updated_at": _now_iso(),
            "last_run_at": "",
        }
        self._load_state()

    def snapshot(self, *, job_stats: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._condition:
            payload = json.loads(json.dumps(self._state, ensure_ascii=True))
            payload["active_runs"] = self._active_runs
        if isinstance(job_stats, dict):
            payload["jobs"] = json.loads(json.dumps(job_stats, ensure_ascii=True))
        return payload

    def update(
        self,
        *,
        paused: bool | None = None,
        pause_reason: str | None = None,
        budget_limit_usd: float | None | object = _UNSET,
        max_active_runs: int | None | object = _UNSET,
    ) -> dict[str, Any]:
        with self._condition:
            if paused is not None:
                self._state["paused"] = bool(paused)
                if not paused and pause_reason is None:
                    self._state["pause_reason"] = ""
            if pause_reason is not None:
                self._state["pause_reason"] = str(pause_reason or "").strip()
            if budget_limit_usd is not _UNSET:
                if budget_limit_usd is None:
                    self._state["budget_limit_usd"] = None
                else:
                    self._state["budget_limit_usd"] = max(0.0, float(budget_limit_usd))
            if max_active_runs is not _UNSET:
                if max_active_runs is None:
                    self._state["max_active_runs"] = None
                else:
                    normalized = max(1, int(max_active_runs))
                    self._state["max_active_runs"] = normalized
            self._state["updated_at"] = _now_iso()
            self._persist_locked()
            self._condition.notify_all()
            return self.snapshot()

    def reset_usage(self) -> dict[str, Any]:
        with self._condition:
            self._state["spend_estimate_usd"] = 0.0
            self._state["llm_calls_total"] = 0
            self._state["runs_total"] = 0
            self._state["per_model"] = {}
            self._state["updated_at"] = _now_iso()
            self._persist_locked()
            self._condition.notify_all()
            return self.snapshot()

    @contextmanager
    def run_guard(self):
        with self._condition:
            while True:
                blocked = self._blocking_reason_locked()
                if blocked is not None:
                    raise RuntimeError(blocked)
                limit = self._state.get("max_active_runs")
                if isinstance(limit, int) and limit > 0 and self._active_runs >= limit:
                    self._condition.wait(timeout=0.1)
                    continue
                self._active_runs += 1
                break
        try:
            yield
        finally:
            with self._condition:
                self._active_runs = max(0, self._active_runs - 1)
                self._condition.notify_all()

    def preflight_error(self) -> str | None:
        with self._condition:
            return self._blocking_reason_locked()

    def record_model_usage(
        self,
        *,
        usage: dict[str, Any] | None,
        strategy: str,
        objective: str = "",
    ) -> dict[str, Any]:
        normalized_usage = usage if isinstance(usage, dict) else {}
        with self._condition:
            total_calls = 0
            total_cost = 0.0
            per_model = self._state.setdefault("per_model", {})
            for model_name, item in normalized_usage.items():
                if not isinstance(item, dict):
                    continue
                calls = max(0, int(item.get("calls", 0) or 0))
                estimated_cost = max(0.0, float(item.get("estimated_cost_usd", 0.0) or 0.0))
                total_calls += calls
                total_cost += estimated_cost
                current = per_model.setdefault(
                    str(model_name),
                    {
                        "calls": 0,
                        "estimated_cost_usd": 0.0,
                        "model_id": str(item.get("model_id") or ""),
                    },
                )
                current["calls"] = int(current.get("calls", 0) or 0) + calls
                current["estimated_cost_usd"] = round(
                    float(current.get("estimated_cost_usd", 0.0) or 0.0) + estimated_cost,
                    6,
                )
                if item.get("model_id"):
                    current["model_id"] = str(item.get("model_id") or "")
            self._state["runs_total"] = int(self._state.get("runs_total", 0) or 0) + 1
            self._state["llm_calls_total"] = int(self._state.get("llm_calls_total", 0) or 0) + total_calls
            self._state["spend_estimate_usd"] = round(
                float(self._state.get("spend_estimate_usd", 0.0) or 0.0) + total_cost,
                6,
            )
            self._state["last_run_at"] = _now_iso()
            self._state["updated_at"] = self._state["last_run_at"]
            if objective:
                self._state["last_objective_preview"] = str(objective).strip()[:220]
            self._state["last_strategy"] = str(strategy or "single")
            self._persist_locked()
            self._condition.notify_all()
            return self.snapshot()

    def _blocking_reason_locked(self) -> str | None:
        if bool(self._state.get("paused")):
            pause_reason = str(self._state.get("pause_reason") or "").strip()
            return pause_reason or "Runtime is paused by operator"
        limit = self._state.get("budget_limit_usd")
        if limit is not None:
            spend = float(self._state.get("spend_estimate_usd", 0.0) or 0.0)
            if spend >= float(limit):
                return "Runtime governance budget limit reached"
        return None

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(loaded, dict):
            return
        for key, value in loaded.items():
            self._state[key] = value

    def _persist_locked(self) -> None:
        if self.state_path is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(self._state, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception:
            return
