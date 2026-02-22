import json
import tempfile
import unittest
from pathlib import Path

from novaadapt_core.benchmark import BenchmarkRunner, run_benchmark


class BenchmarkTests(unittest.TestCase):
    def test_run_suite_scores_tasks(self):
        outputs = {
            "task-a": {
                "actions": [{"type": "click", "target": "Browser"}],
                "results": [{"status": "preview"}],
                "model": "m1",
                "strategy": "single",
            },
            "task-b": {
                "actions": [{"type": "note", "target": "empty_plan"}],
                "results": [{"status": "preview"}],
                "model": "m2",
                "strategy": "single",
            },
        }

        def run_fn(payload):
            objective = payload["objective"]
            if "A" in objective:
                return outputs["task-a"]
            return outputs["task-b"]

        tasks = [
            {
                "id": "task-a",
                "objective": "Task A objective",
                "expected_action_types": ["click"],
                "expected_target_contains": ["browser"],
            },
            {
                "id": "task-b",
                "objective": "Task B objective",
                "expected_action_types": ["click"],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            suite = Path(tmp) / "suite.json"
            suite.write_text(json.dumps({"tasks": tasks}))
            result = run_benchmark(run_fn=run_fn, suite_path=suite)

        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(result["summary"]["passed"], 1)
        self.assertEqual(result["summary"]["failed"], 1)

    def test_output_written(self):
        def run_fn(_payload):
            return {
                "actions": [{"type": "click", "target": "ok"}],
                "results": [{"status": "preview"}],
                "model": "m1",
                "strategy": "single",
            }

        with tempfile.TemporaryDirectory() as tmp:
            suite_path = Path(tmp) / "suite.json"
            out_path = Path(tmp) / "report.json"
            suite_path.write_text(
                json.dumps({"tasks": [{"id": "t", "objective": "Task", "expected_action_types": ["click"]}]})
            )

            result = run_benchmark(run_fn=run_fn, suite_path=suite_path, output_path=out_path)
            self.assertTrue(out_path.exists())
            written = json.loads(out_path.read_text())
            self.assertEqual(written["summary"]["total"], result["summary"]["total"])

    def test_runner_handles_task_exceptions(self):
        def run_fn(_payload):
            raise RuntimeError("endpoint unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            suite_path = Path(tmp) / "suite.json"
            suite_path.write_text(
                json.dumps({"tasks": [{"id": "t", "objective": "Task"}]})
            )
            result = run_benchmark(run_fn=run_fn, suite_path=suite_path)

        self.assertEqual(result["summary"]["failed"], 1)
        self.assertIn("run_error", result["tasks"][0])


if __name__ == "__main__":
    unittest.main()
