from __future__ import annotations

from unittest import TestCase

from novaadapt_core.server_canvas_routes import get_canvas_frames, get_canvas_status, post_canvas_render


class _StubHandler:
    def __init__(self) -> None:
        self.last_status = 0
        self.last_payload: dict[str, object] | None = None

    def _send_json(self, status: int, payload: dict[str, object]):
        self.last_status = int(status)
        self.last_payload = payload


class _StubService:
    def __init__(self) -> None:
        self.status_calls: list[str] = []
        self.frames_calls: list[dict[str, object]] = []
        self.render_calls: list[dict[str, object]] = []

    def canvas_status(self, *, context: str = "api"):
        self.status_calls.append(context)
        return {"ok": True, "enabled": False, "context": context}

    def canvas_frames(self, session_id: str, *, limit: int = 20, context: str = "api"):
        self.frames_calls.append({"session_id": session_id, "limit": limit, "context": context})
        return {"ok": True, "session_id": session_id, "count": 0, "frames": []}

    def canvas_render(
        self,
        title: str,
        *,
        session_id: str = "default",
        sections=None,
        footer: str = "",
        metadata=None,
        context: str = "api",
    ):
        self.render_calls.append(
            {
                "title": title,
                "session_id": session_id,
                "sections": sections,
                "footer": footer,
                "metadata": metadata,
                "context": context,
            }
        )
        return {"ok": True, "title": title, "session_id": session_id}


def _single(query: dict[str, list[str]], key: str):
    values = query.get(key) or []
    return values[0] if values else None


class CanvasRouteTests(TestCase):
    def test_get_canvas_status(self):
        handler = _StubHandler()
        service = _StubService()
        status = get_canvas_status(handler, service, _single, {"context": ["cli"]})
        self.assertEqual(status, 200)
        self.assertEqual(handler.last_status, 200)
        self.assertEqual(service.status_calls, ["cli"])

    def test_get_canvas_frames_requires_session_id(self):
        handler = _StubHandler()
        service = _StubService()
        with self.assertRaisesRegex(ValueError, "'session_id' is required"):
            get_canvas_frames(handler, service, _single, {})

    def test_post_canvas_render(self):
        handler = _StubHandler()
        service = _StubService()
        status = post_canvas_render(
            handler,
            service,
            {
                "title": "Aetherion board",
                "session_id": "sess-1",
                "sections": [{"heading": "Trade", "body": "stable"}],
                "metadata": {"realm": "aetherion"},
                "context": "api",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(handler.last_status, 200)
        self.assertEqual(service.render_calls[0]["session_id"], "sess-1")


if __name__ == "__main__":
    import unittest

    unittest.main()
