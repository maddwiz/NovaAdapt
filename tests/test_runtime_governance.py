import tempfile
import threading
import unittest
from pathlib import Path

from novaadapt_core.directshell import ExecutionResult
from novaadapt_core.runtime_governance import RuntimeGovernance
from novaadapt_core.service import NovaAdaptService
from novaadapt_shared.model_router import RouterResult


class _StubRouter:
    def list_models(self):
        class Model:
            def __init__(self, name, model, provider, base_url):
                self.name = name
                self.model = model
                self.provider = provider
                self.base_url = base_url

        return [Model("local", "qwen", "openai-compatible", "http://localhost:11434/v1")]

    def health_check(self, model_names=None, probe_prompt="Reply with: OK"):
        return [{"name": "local", "ok": True, "latency_ms": 1.0}]

    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
        return RouterResult(
            model_name=model_name or "local",
            model_id="qwen",
            content='{"actions":[{"type":"click","target":"OK"}]}',
            strategy=strategy,
            attempted_models=[model_name or "local"],
            usage={
                model_name or "local": {
                    "calls": 1,
                    "model_id": "qwen",
                    "estimated_cost_usd": 0.03,
                }
            },
            estimated_cost_usd=0.03,
        )


class _StubDirectShell:
    def execute_action(self, action, dry_run=True):
        return ExecutionResult(action=action, status="preview" if dry_run else "ok", output="simulated")


class RuntimeGovernanceTests(unittest.TestCase):
    def test_snapshot_update_and_reset_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "runtime_governance.json"
            governance = RuntimeGovernance(state_path)
            updated = governance.update(paused=True, pause_reason="ops freeze", budget_limit_usd=2.5, max_active_runs=2)
            self.assertTrue(updated["paused"])
            self.assertEqual(updated["pause_reason"], "ops freeze")
            self.assertEqual(updated["budget_limit_usd"], 2.5)
            self.assertEqual(updated["max_active_runs"], 2)

            governance.record_model_usage(
                usage={"local": {"calls": 2, "model_id": "qwen", "estimated_cost_usd": 0.06}},
                strategy="single",
                objective="demo",
            )
            snap = governance.snapshot()
            self.assertEqual(snap["llm_calls_total"], 2)
            self.assertEqual(snap["runs_total"], 1)
            self.assertEqual(snap["per_model"]["local"]["calls"], 2)

            reset = governance.reset_usage()
            self.assertEqual(reset["llm_calls_total"], 0)
            self.assertEqual(reset["runs_total"], 0)
            self.assertFalse(reset["per_model"])

    def test_run_guard_honors_pause_and_concurrency_limit(self):
        governance = RuntimeGovernance()
        governance.update(max_active_runs=1)
        entered_second = threading.Event()
        release_first = threading.Event()

        def first():
            with governance.run_guard():
                release_first.wait(timeout=2)

        def second():
            with governance.run_guard():
                entered_second.set()

        first_thread = threading.Thread(target=first)
        second_thread = threading.Thread(target=second)
        first_thread.start()
        second_thread.start()
        self.assertFalse(entered_second.wait(timeout=0.2))
        release_first.set()
        self.assertTrue(entered_second.wait(timeout=2))
        first_thread.join(timeout=2)
        second_thread.join(timeout=2)

        governance.update(paused=True, pause_reason="manual pause")
        with self.assertRaisesRegex(RuntimeError, "manual pause"):
            with governance.run_guard():
                pass

    def test_service_records_usage_and_blocks_when_paused(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path(tmp) / "unused.json",
                db_path=Path(tmp) / "actions.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            result = service.run({"objective": "demo"})
            self.assertEqual(result["model"], "local")
            state = service.runtime_governance_status()
            self.assertEqual(state["runs_total"], 1)
            self.assertEqual(state["llm_calls_total"], 1)
            self.assertAlmostEqual(state["spend_estimate_usd"], 0.03, places=6)

            service.runtime_governance_update(paused=True, pause_reason="ops freeze")
            with self.assertRaisesRegex(RuntimeError, "ops freeze"):
                service.run({"objective": "blocked"})


if __name__ == "__main__":
    unittest.main()
