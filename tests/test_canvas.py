from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from novaadapt_core.canvas import (
    CanvasActionError,
    CanvasActionRouter,
    CanvasRenderer,
    CanvasSessionStore,
    canvas_enabled,
)


class CanvasTests(unittest.TestCase):
    def test_canvas_enabled_flag_resolution(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NOVAADAPT_ENABLE_CANVAS", None)
            os.environ.pop("NOVAADAPT_ENABLE_CANVAS_API", None)
            self.assertFalse(canvas_enabled(context="api"))

        with patch.dict(os.environ, {"NOVAADAPT_ENABLE_CANVAS": "1"}, clear=False):
            self.assertTrue(canvas_enabled(context="api"))
            self.assertTrue(canvas_enabled(context="mcp"))

        with patch.dict(os.environ, {"NOVAADAPT_ENABLE_CANVAS_MCP": "1"}, clear=False):
            self.assertFalse(canvas_enabled(context="api"))
            self.assertTrue(canvas_enabled(context="mcp"))

    def test_renderer_escapes_html(self) -> None:
        renderer = CanvasRenderer()
        frame = renderer.render(
            "<script>alert(1)</script>",
            sections=[{"heading": "H", "body": "<b>unsafe</b>"}],
            footer="done",
        )
        self.assertTrue(frame.frame_id.startswith("frame-"))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", frame.html)
        self.assertIn("&lt;b&gt;unsafe&lt;/b&gt;", frame.html)
        self.assertNotIn("<script>alert(1)</script>", frame.html)

    def test_action_router_dispatch(self) -> None:
        router = CanvasActionRouter()
        router.register("open_panel", lambda payload: {"ok": True, "payload": payload})
        out = router.dispatch("open_panel", {"panel": "market"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["payload"]["panel"], "market")
        with self.assertRaises(CanvasActionError):
            router.dispatch("unknown", {})

    def test_session_store_max_frames(self) -> None:
        renderer = CanvasRenderer()
        store = CanvasSessionStore(max_frames_per_session=2)
        store.push("sess-1", renderer.render("one"))
        store.push("sess-1", renderer.render("two"))
        latest = store.push("sess-1", renderer.render("three"))
        frames = store.list("sess-1", limit=10)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[-1].frame_id, latest.frame_id)


if __name__ == "__main__":
    unittest.main()
