import json
import tempfile
import unittest
from pathlib import Path

from novaadapt_core.benchmark import (
    BenchmarkRunner,
    compare_benchmark_reports,
    load_benchmark_report,
    render_benchmark_comparison_markdown,
    run_benchmark,
    write_benchmark_comparison_markdown,
)


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

    def test_load_and_compare_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            primary_path = Path(tmp) / "primary.json"
            baseline_path = Path(tmp) / "baseline.json"
            primary_path.write_text(
                json.dumps(
                    {
                        "summary": {
                            "total": 10,
                            "passed": 9,
                            "failed": 1,
                            "success_rate": 0.9,
                            "first_try_success_rate": 0.9,
                            "avg_action_count": 4.2,
                            "blocked_count": 1,
                        }
                    }
                )
            )
            baseline_path.write_text(
                json.dumps(
                    {
                        "summary": {
                            "total": 10,
                            "passed": 6,
                            "failed": 4,
                            "success_rate": 0.6,
                            "first_try_success_rate": 0.6,
                            "avg_action_count": 5.0,
                            "blocked_count": 2,
                        }
                    }
                )
            )

            primary = load_benchmark_report(primary_path)
            baseline = load_benchmark_report(baseline_path)
            compared = compare_benchmark_reports(
                primary_name="NovaAdapt",
                primary_report=primary,
                baselines={"OtherAgent": baseline},
            )

        self.assertEqual(compared["summary"]["primary"], "NovaAdapt")
        self.assertEqual(compared["table"][0]["name"], "NovaAdapt")
        self.assertGreater(compared["deltas"]["OtherAgent"]["success_rate_delta_vs_primary"], 0)

    def test_render_and_write_comparison_markdown(self):
        report = {
            "summary": {
                "primary": "NovaAdapt",
                "competitors": ["OtherAgent"],
                "ranked_by": "success_rate",
            },
            "table": [
                {
                    "name": "NovaAdapt",
                    "total": 10,
                    "passed": 9,
                    "failed": 1,
                    "success_rate": 0.9,
                    "first_try_success_rate": 0.9,
                    "avg_action_count": 4.2,
                    "blocked_count": 1,
                },
                {
                    "name": "OtherAgent",
                    "total": 10,
                    "passed": 6,
                    "failed": 4,
                    "success_rate": 0.6,
                    "first_try_success_rate": 0.6,
                    "avg_action_count": 5.0,
                    "blocked_count": 2,
                },
            ],
            "deltas": {
                "OtherAgent": {
                    "success_rate_delta_vs_primary": 0.3,
                    "first_try_success_rate_delta_vs_primary": 0.3,
                }
            },
        }

        markdown = render_benchmark_comparison_markdown(report, title="Bench Run")
        self.assertIn("# Bench Run", markdown)
        self.assertIn("| Rank | System | Success |", markdown)
        self.assertIn("| 1 | NovaAdapt | 90.00% |", markdown)
        self.assertIn("| 2 | OtherAgent | 60.00% |", markdown)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "report.md"
            written_path = write_benchmark_comparison_markdown(report, out_path, title="Bench Run")
            self.assertEqual(written_path, out_path)
            self.assertTrue(out_path.exists())
            text = out_path.read_text()
            self.assertIn("Bench Run", text)
            self.assertIn("Delta vs Primary", text)


if __name__ == "__main__":
    unittest.main()
