import tempfile
import unittest
from pathlib import Path

from novaadapt_core.audit_store import AuditStore
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


class _FlakyDirectShell:
    def __init__(self, fail_count=1):
        self.fail_count = max(0, int(fail_count))
        self.execute_calls = 0

    def execute_action(self, action, dry_run=True):
        if dry_run:
            return ExecutionResult(action=action, status="preview", output="simulated")
        self.execute_calls += 1
        if self.execute_calls <= self.fail_count:
            return ExecutionResult(action=action, status="failed", output="transient failure")
        return ExecutionResult(action=action, status="ok", output="recovered")


class _StubDirectShellWithProbe(_StubDirectShell):
    def probe(self):
        return {"ok": True, "transport": "stub"}


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

    def test_directshell_probe(self):
        service = NovaAdaptService(
            default_config=Path("unused.json"),
            router_loader=lambda _path: _StubRouter(),
            directshell_factory=_StubDirectShellWithProbe,
        )
        probe = service.directshell_probe()
        self.assertTrue(probe["ok"])
        self.assertEqual(probe["transport"], "stub")

    def test_directshell_probe_handles_missing_probe_method(self):
        service = NovaAdaptService(
            default_config=Path("unused.json"),
            router_loader=lambda _path: _StubRouter(),
            directshell_factory=_StubDirectShell,
        )
        probe = service.directshell_probe()
        self.assertFalse(probe["ok"])
        self.assertIn("not implemented", probe["error"])

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

    def test_approve_plan_marks_failed_on_blocked_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            # Store a dangerous action directly so approval execution hits policy block.
            plan = service._plans().create(
                {
                    "objective": "dangerous",
                    "actions": [{"type": "delete", "target": "/tmp/something"}],
                }
            )
            out = service.approve_plan(plan["id"], {"execute": True, "allow_dangerous": False})
            self.assertEqual(out["status"], "failed")
            self.assertEqual(out["progress_completed"], 1)
            self.assertEqual(out["progress_total"], 1)
            self.assertIn("failed or were blocked", str(out.get("execution_error")))

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
            self.assertEqual(approved.get("progress_completed"), 1)
            self.assertEqual(approved.get("progress_total"), 1)
            self.assertIsNone(approved.get("execution_error"))

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

    def test_approve_plan_retries_transient_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            flaky = _FlakyDirectShell(fail_count=1)
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=lambda: flaky,
            )

            created = service.create_plan({"objective": "click ok"})
            approved = service.approve_plan(
                created["id"],
                {
                    "execute": True,
                    "action_retry_attempts": 2,
                    "action_retry_backoff_seconds": 0.0,
                },
            )
            self.assertEqual(approved["status"], "executed")
            self.assertEqual(approved["execution_results"][0]["status"], "ok")
            self.assertEqual(approved["execution_results"][0]["attempts"], 2)
            self.assertEqual(flaky.execute_calls, 2)

    def test_approve_plan_retry_exhaustion_marks_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            flaky = _FlakyDirectShell(fail_count=3)
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=lambda: flaky,
            )

            created = service.create_plan({"objective": "click ok"})
            out = service.approve_plan(
                created["id"],
                {
                    "execute": True,
                    "action_retry_attempts": 1,
                    "action_retry_backoff_seconds": 0.0,
                },
            )
            self.assertEqual(out["status"], "failed")
            self.assertEqual(out["execution_results"][0]["status"], "failed")
            self.assertEqual(out["execution_results"][0]["attempts"], 2)
            self.assertEqual(flaky.execute_calls, 2)

    def test_events_reads_filtered_audit_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_db = Path(tmp) / "events.db"
            store = AuditStore(events_db)
            first = store.append(
                category="run",
                action="run_async",
                status="ok",
                entity_type="job",
                entity_id="job-1",
            )
            store.append(
                category="plans",
                action="approve",
                status="ok",
                entity_type="plan",
                entity_id="plan-1",
            )

            service = NovaAdaptService(
                default_config=Path("unused.json"),
                audit_db_path=events_db,
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )

            plan_events = service.events(limit=10, category="plans")
            self.assertEqual(len(plan_events), 1)
            self.assertEqual(plan_events[0]["entity_id"], "plan-1")

            newer_events = service.events(limit=10, since_id=first["id"])
            self.assertEqual(len(newer_events), 1)
            self.assertEqual(newer_events[0]["category"], "plans")

    def test_events_wait_returns_new_rows_or_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_db = Path(tmp) / "events.db"
            store = AuditStore(events_db)
            first = store.append(
                category="run",
                action="run_async",
                status="ok",
                entity_type="job",
                entity_id="job-1",
            )
            second = store.append(
                category="plans",
                action="approve",
                status="ok",
                entity_type="plan",
                entity_id="plan-1",
            )

            service = NovaAdaptService(
                default_config=Path("unused.json"),
                audit_db_path=events_db,
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )

            rows = service.events_wait(since_id=first["id"], timeout_seconds=0.2, interval_seconds=0.01)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["id"], second["id"])

            timed_out = service.events_wait(since_id=second["id"], timeout_seconds=0.1, interval_seconds=0.01)
            self.assertEqual(timed_out, [])


if __name__ == "__main__":
    unittest.main()
