from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novaadapt_core.service import NovaAdaptService


class ServiceVoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.service = NovaAdaptService(
            default_config=Path("unused.json"),
            db_path=Path(self._tmp.name) / "actions.db",
            plans_db_path=Path(self._tmp.name) / "plans.db",
        )

    def test_voice_status_disabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            status = self.service.voice_status(context="api")
        self.assertTrue(status["ok"])
        self.assertFalse(status["enabled"])

    def test_voice_transcribe_requires_flag(self):
        with mock.patch.dict(os.environ, {"NOVAADAPT_STT_BACKEND": "static", "NOVAADAPT_STT_STATIC_TEXT": "x"}, clear=False):
            with self.assertRaisesRegex(ValueError, "voice feature disabled"):
                self.service.voice_transcribe("/tmp/in.wav", context="cli")

    def test_voice_transcribe_static_backend(self):
        with mock.patch.dict(
            os.environ,
            {
                "NOVAADAPT_ENABLE_VOICE_CLI": "1",
                "NOVAADAPT_STT_BACKEND": "static",
                "NOVAADAPT_STT_STATIC_TEXT": "hello adapt",
                "NOVAADAPT_STT_STATIC_CONFIDENCE": "0.8",
            },
            clear=False,
        ):
            out = self.service.voice_transcribe("/tmp/in.wav", context="cli", hints=["map"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["text"], "hello adapt")
        self.assertAlmostEqual(float(out["confidence"] or 0.0), 0.8, places=2)

    def test_voice_synthesize_static_backend(self):
        output_path = Path(self._tmp.name) / "voice.txt"
        with mock.patch.dict(
            os.environ,
            {
                "NOVAADAPT_ENABLE_VOICE_CLI": "1",
                "NOVAADAPT_TTS_BACKEND": "static",
            },
            clear=False,
        ):
            out = self.service.voice_synthesize(
                "route confirmed",
                output_path=str(output_path),
                context="cli",
                voice="alloy",
            )
        self.assertTrue(out["ok"])
        self.assertEqual(out["output_path"], str(output_path))
        self.assertTrue(output_path.exists())
        self.assertEqual(output_path.read_text(encoding="utf-8"), "route confirmed")


if __name__ == "__main__":
    unittest.main()
