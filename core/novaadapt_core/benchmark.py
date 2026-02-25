from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Callable


@dataclass(frozen=True)
class BenchmarkTask:
    id: str
    objective: str
    strategy: str = "single"
    model: str | None = None
    candidates: list[str] | None = None
    fallbacks: list[str] | None = None
    max_actions: int = 25
    expected_action_types: list[str] | None = None
    expected_target_contains: list[str] | None = None


class BenchmarkRunner:
    """Runs repeatable objective suites against NovaAdapt run payloads."""

    def __init__(self, run_fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self._run_fn = run_fn

    @staticmethod
    def load_suite(path: str | Path) -> list[BenchmarkTask]:
        raw = json.loads(Path(path).read_text())
        items = raw["tasks"] if isinstance(raw, dict) else raw
        tasks: list[BenchmarkTask] = []
        for index, item in enumerate(items):
            tasks.append(
                BenchmarkTask(
                    id=str(item.get("id", f"task-{index+1}")),
                    objective=str(item["objective"]),
                    strategy=str(item.get("strategy", "single")),
                    model=item.get("model"),
                    candidates=item.get("candidates"),
                    fallbacks=item.get("fallbacks"),
                    max_actions=int(item.get("max_actions", 25)),
                    expected_action_types=item.get("expected_action_types"),
                    expected_target_contains=item.get("expected_target_contains"),
                )
            )
        return tasks

    def run_suite(self, tasks: list[BenchmarkTask]) -> dict[str, Any]:
        per_task: list[dict[str, Any]] = []
        passed = 0
        action_counts: list[int] = []
        blocked = 0

        for task in tasks:
            payload = {
                "objective": task.objective,
                "strategy": task.strategy,
                "model": task.model,
                "candidates": task.candidates or [],
                "fallbacks": task.fallbacks or [],
                "execute": False,
                "allow_dangerous": False,
                "max_actions": max(1, task.max_actions),
            }
            try:
                output = self._run_fn(payload)
                run_error: str | None = None
            except Exception as exc:
                output = {"actions": [], "results": []}
                run_error = str(exc)
            score = self._score_task(task=task, output=output)
            if run_error is not None:
                score["passed"] = False
                score["run_error"] = run_error
            passed += 1 if score["passed"] else 0
            action_counts.append(score["action_count"])
            blocked += 1 if score["blocked"] else 0
            per_task.append(
                {
                    "id": task.id,
                    "objective": task.objective,
                    **score,
                    "model": output.get("model"),
                    "strategy": output.get("strategy"),
                }
            )

        total = len(tasks)
        success_rate = (passed / total) if total else 0.0

        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "success_rate": round(success_rate, 4),
                "first_try_success_rate": round(success_rate, 4),
                "avg_action_count": round(mean(action_counts), 3) if action_counts else 0.0,
                "blocked_count": blocked,
            },
            "tasks": per_task,
        }

    def _score_task(self, task: BenchmarkTask, output: dict[str, Any]) -> dict[str, Any]:
        actions = output.get("actions", [])
        if not isinstance(actions, list):
            actions = []

        action_types = [str(item.get("type", "")).lower() for item in actions if isinstance(item, dict)]
        targets = [str(item.get("target", "")).lower() for item in actions if isinstance(item, dict)]

        has_meaningful_action = any(item not in {"note", ""} for item in action_types)

        type_ok = True
        if task.expected_action_types:
            required = [item.lower() for item in task.expected_action_types]
            type_ok = all(req in action_types for req in required)

        target_ok = True
        if task.expected_target_contains:
            joined = "\n".join(targets)
            required_targets = [item.lower() for item in task.expected_target_contains]
            target_ok = all(req in joined for req in required_targets)

        results = output.get("results", [])
        blocked = False
        if isinstance(results, list):
            blocked = any(isinstance(item, dict) and item.get("status") == "blocked" for item in results)

        passed = bool(has_meaningful_action and type_ok and target_ok and not blocked)

        return {
            "passed": passed,
            "action_count": len(actions),
            "blocked": blocked,
            "has_meaningful_action": has_meaningful_action,
            "type_requirements_met": type_ok,
            "target_requirements_met": target_ok,
        }


def run_benchmark(
    run_fn: Callable[[dict[str, Any]], dict[str, Any]],
    suite_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    runner = BenchmarkRunner(run_fn=run_fn)
    tasks = runner.load_suite(suite_path)
    result = runner.run_suite(tasks)
    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(result, indent=2))
    return result


def load_benchmark_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"benchmark report is not an object: {path}")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError(f"benchmark report missing summary object: {path}")
    return payload


def compare_benchmark_reports(
    *,
    primary_name: str,
    primary_report: dict[str, Any],
    baselines: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    def _metric(summary: dict[str, Any], key: str) -> float:
        value = summary.get(key, 0.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    rows: list[dict[str, Any]] = []
    primary_summary = primary_report.get("summary") if isinstance(primary_report, dict) else None
    if not isinstance(primary_summary, dict):
        raise ValueError("primary benchmark report missing summary")

    def _row(name: str, report: dict[str, Any]) -> dict[str, Any]:
        summary = report.get("summary")
        if not isinstance(summary, dict):
            raise ValueError(f"benchmark report for '{name}' missing summary")
        return {
            "name": name,
            "total": int(summary.get("total", 0) or 0),
            "passed": int(summary.get("passed", 0) or 0),
            "failed": int(summary.get("failed", 0) or 0),
            "success_rate": round(_metric(summary, "success_rate"), 4),
            "first_try_success_rate": round(_metric(summary, "first_try_success_rate"), 4),
            "avg_action_count": round(_metric(summary, "avg_action_count"), 3),
            "blocked_count": int(summary.get("blocked_count", 0) or 0),
        }

    rows.append(_row(primary_name, primary_report))
    for name in sorted(baselines.keys()):
        rows.append(_row(name, baselines[name]))

    rows.sort(key=lambda item: (item["success_rate"], item["first_try_success_rate"]), reverse=True)

    primary_success = _metric(primary_summary, "success_rate")
    deltas: dict[str, dict[str, float]] = {}
    for name, report in baselines.items():
        summary = report.get("summary")
        if not isinstance(summary, dict):
            continue
        deltas[name] = {
            "success_rate_delta_vs_primary": round(primary_success - _metric(summary, "success_rate"), 4),
            "first_try_success_rate_delta_vs_primary": round(
                _metric(primary_summary, "first_try_success_rate") - _metric(summary, "first_try_success_rate"),
                4,
            ),
        }

    return {
        "summary": {
            "primary": primary_name,
            "competitors": sorted(baselines.keys()),
            "ranked_by": "success_rate",
        },
        "table": rows,
        "deltas": deltas,
    }
