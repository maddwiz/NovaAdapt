from __future__ import annotations

from unittest import TestCase

from novaadapt_core.server_voice_routes import (
    get_voice_status,
    post_voice_synthesize,
    post_voice_transcribe,
)


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
        self.transcribe_calls: list[dict[str, object]] = []
        self.synthesize_calls: list[dict[str, object]] = []

    def voice_status(self, *, context: str = "api"):
        self.status_calls.append(context)
        return {"ok": True, "enabled": False, "context": context}

    def voice_transcribe(self, audio_path: str, *, hints, metadata, backend: str = "", context: str = "api"):
        self.transcribe_calls.append(
            {
                "audio_path": audio_path,
                "hints": hints,
                "metadata": metadata,
                "backend": backend,
                "context": context,
            }
        )
        return {"ok": True, "text": "hello"}

    def voice_synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata=None,
        backend: str = "",
        context: str = "api",
    ):
        self.synthesize_calls.append(
            {
                "text": text,
                "output_path": output_path,
                "voice": voice,
                "metadata": metadata,
                "backend": backend,
                "context": context,
            }
        )
        return {"ok": True, "output_path": output_path}


def _single(query: dict[str, list[str]], key: str):
    values = query.get(key) or []
    return values[0] if values else None


class VoiceRouteTests(TestCase):
    def test_get_voice_status_passes_context(self):
        handler = _StubHandler()
        service = _StubService()
        status = get_voice_status(handler, service, _single, {"context": ["cli"]})
        self.assertEqual(status, 200)
        self.assertEqual(handler.last_status, 200)
        self.assertEqual(service.status_calls, ["cli"])

    def test_post_voice_transcribe_parses_hints_string(self):
        handler = _StubHandler()
        service = _StubService()
        status = post_voice_transcribe(
            handler,
            service,
            {
                "audio_path": "/tmp/input.wav",
                "hints": "nav,combat",
                "metadata": {"realm": "game_world"},
                "backend": "static",
                "context": "api",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(handler.last_status, 200)
        self.assertEqual(len(service.transcribe_calls), 1)
        call = service.transcribe_calls[0]
        self.assertEqual(call["hints"], ["nav", "combat"])
        self.assertEqual(call["backend"], "static")

    def test_post_voice_synthesize_requires_text(self):
        handler = _StubHandler()
        service = _StubService()
        with self.assertRaisesRegex(ValueError, "'text' is required"):
            post_voice_synthesize(handler, service, {"output_path": "/tmp/out.mp3"})


if __name__ == "__main__":
    import unittest

    unittest.main()
