import tempfile
import unittest
from pathlib import Path

from novaadapt_core.directshell import ExecutionResult
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
        return [
            {
                "name": "local",
                "model": "qwen",
                "provider": "openai-compatible",
                "ok": True,
                "latency_ms": 1.2,
                "preview": "OK",
            }
        ]

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
            content='{"actions":[{"type":"click","target":"OK","undo":{"type":"hotkey","target":"cmd+z"}}]}',
            strategy=strategy,
            votes={},
            errors={},
            attempted_models=[model_name or "local"],
        )


class _StubDirectShell:
    def execute_action(self, action, dry_run=True):
        return ExecutionResult(
            action=action,
            status="preview" if dry_run else "ok",
            output="simulated",
        )


class ServiceTests(unittest.TestCase):
    def test_models_and_check(self):
        service = NovaAdaptService(
            default_config=Path("unused.json"),
            router_loader=lambda _path: _StubRouter(),
            directshell_factory=_StubDirectShell,
        )

        models = service.models()
        self.assertEqual(models[0]["name"], "local")

        check = service.check()
        self.assertTrue(check[0]["ok"])

    def test_run_records_history_and_undo_mark_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )

            out = service.run({"objective": "click ok"})
            self.assertEqual(out["results"][0]["status"], "preview")

            history = service.history(limit=5)
            self.assertEqual(len(history), 1)
            self.assertIsNotNone(history[0]["undo_action"])

            undo = service.undo({"mark_only": True})
            self.assertEqual(undo["status"], "marked_undone")

    def test_run_requires_objective(self):
        service = NovaAdaptService(
            default_config=Path("unused.json"),
            router_loader=lambda _path: _StubRouter(),
            directshell_factory=_StubDirectShell,
        )
        with self.assertRaises(ValueError):
            service.run({})

    def test_plan_lifecycle_execute_and_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )

            created = service.create_plan({"objective": "click ok"})
            self.assertEqual(created["status"], "pending")
            self.assertEqual(created["objective"], "click ok")

            # Plan generation does not write to action history.
            self.assertEqual(service.history(limit=5), [])

            listed = service.list_plans(limit=5)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], created["id"])

            approved = service.approve_plan(created["id"], {"execute": True})
            self.assertEqual(approved["status"], "executed")
            self.assertEqual(len(approved.get("execution_results") or []), 1)
            self.assertEqual(len(approved.get("action_log_ids") or []), 1)

            history = service.history(limit=5)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["status"], "ok")

            undone = service.undo_plan(created["id"], {"mark_only": True})
            self.assertEqual(undone["plan_id"], created["id"])
            self.assertTrue(all(item["ok"] for item in undone["results"]))

            created_2 = service.create_plan({"objective": "click ok again"})
            rejected = service.reject_plan(created_2["id"], reason="operator rejected")
            self.assertEqual(rejected["status"], "rejected")
            self.assertEqual(rejected["reject_reason"], "operator rejected")

            with self.assertRaises(ValueError):
                service.approve_plan(created_2["id"], {"execute": True})


if __name__ == "__main__":
    unittest.main()
