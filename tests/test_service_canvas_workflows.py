from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from novaadapt_core.service import NovaAdaptService


class ServiceCanvasWorkflowTests(unittest.TestCase):
    def test_canvas_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(default_config=Path(tmp) / "models.local.json")
            with self.assertRaisesRegex(ValueError, "canvas feature disabled"):
                service.canvas_render("hello", context="cli")

    def test_canvas_render_and_frames_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"NOVAADAPT_ENABLE_CANVAS_CLI": "1"}, clear=False):
                service = NovaAdaptService(default_config=Path(tmp) / "models.local.json")
                rendered = service.canvas_render(
                    "Aetherion Panel",
                    session_id="s1",
                    sections=[{"heading": "Trade", "body": "stable"}],
                    context="cli",
                )
                self.assertTrue(rendered["ok"])
                frames = service.canvas_frames("s1", context="cli")
                self.assertEqual(frames["count"], 1)

    def test_workflows_start_advance_resume_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"NOVAADAPT_ENABLE_WORKFLOWS_CLI": "1"}, clear=False):
                service = NovaAdaptService(
                    default_config=Path(tmp) / "models.local.json",
                    db_path=Path(tmp) / "service.sqlite3",
                )
                started = service.workflows_start(
                    "Route patrol",
                    steps=[{"name": "scan"}, {"name": "report"}],
                    context="cli",
                )
                self.assertTrue(started["ok"])
                workflow_id = str(started["workflow_id"])

                advanced = service.workflows_advance(workflow_id, result={"ok": True}, context="cli")
                self.assertTrue(advanced["ok"])
                listed = service.workflows_list(context="cli")
                self.assertGreaterEqual(listed["count"], 1)
                resumed = service.workflows_resume(workflow_id, context="cli")
                self.assertTrue(resumed["ok"])


if __name__ == "__main__":
    unittest.main()
