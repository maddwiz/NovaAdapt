from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from novaadapt_core.workflows import (
    WorkflowCheckpointStore,
    WorkflowEngine,
    WorkflowStore,
    workflows_enabled,
)


class WorkflowTests(unittest.TestCase):
    def test_workflows_enabled_flag_resolution(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOVAADAPT_ENABLE_WORKFLOWS", None)
            os.environ.pop("NOVAADAPT_ENABLE_WORKFLOWS_API", None)
            self.assertFalse(workflows_enabled(context="api"))

        with patch.dict(os.environ, {"NOVAADAPT_ENABLE_WORKFLOWS": "1"}, clear=False):
            self.assertTrue(workflows_enabled(context="api"))
            self.assertTrue(workflows_enabled(context="mcp"))

        with patch.dict(os.environ, {"NOVAADAPT_ENABLE_WORKFLOWS_CLI": "1"}, clear=False):
            self.assertTrue(workflows_enabled(context="cli"))
            self.assertFalse(workflows_enabled(context="api"))

    def test_store_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "workflows.sqlite3")
            store = WorkflowStore(db_path)
            created = store.create(
                "build route plan",
                steps=[{"name": "analyze"}, {"name": "draft"}],
                context={"source": "test"},
            )
            self.assertEqual(created.status, "queued")
            loaded = store.get(created.workflow_id)
            assert loaded is not None
            self.assertEqual(len(loaded.steps), 2)
            updated = store.update(created.workflow_id, status="running")
            assert updated is not None
            self.assertEqual(updated.status, "running")
            listed = store.list(limit=5)
            self.assertEqual(len(listed), 1)

    def test_checkpoints_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "checkpoints.sqlite3")
            cps = WorkflowCheckpointStore(db_path)
            cps.save("wf-1", "start", {"state": "queued"})
            cps.save("wf-1", "step-1", {"state": "running"})
            loaded = cps.load("wf-1", "step-1")
            assert loaded is not None
            self.assertEqual(loaded["payload"]["state"], "running")
            latest = cps.latest("wf-1")
            assert latest is not None
            self.assertEqual(latest["checkpoint_id"], "step-1")

    def test_engine_advance_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "engine.sqlite3")
            store = WorkflowStore(db_path)
            checkpoints = WorkflowCheckpointStore(db_path)
            engine = WorkflowEngine(store, checkpoints=checkpoints)

            started = engine.start(
                "mesh patrol workflow",
                steps=[{"name": "scan"}, {"name": "report"}],
                context={"realm": "aetherion"},
            )
            self.assertEqual(started.status, "queued")

            step1 = engine.advance(started.workflow_id, result={"ok": True})
            assert step1 is not None
            self.assertEqual(step1.status, "running")
            self.assertEqual(step1.context["current_step"], 1)

            step2 = engine.advance(started.workflow_id, result={"ok": True})
            assert step2 is not None
            self.assertEqual(step2.status, "done")
            self.assertEqual(step2.context["current_step"], 2)

            latest = checkpoints.latest(started.workflow_id)
            assert latest is not None
            self.assertEqual(latest["payload"]["status"], "done")

    def test_engine_fail_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "engine_fail.sqlite3")
            store = WorkflowStore(db_path)
            engine = WorkflowEngine(store)
            started = engine.start("fail me", steps=[{"name": "step"}])
            failed = engine.advance(started.workflow_id, error="boom")
            assert failed is not None
            self.assertEqual(failed.status, "failed")
            self.assertEqual(failed.last_error, "boom")


if __name__ == "__main__":
    unittest.main()
