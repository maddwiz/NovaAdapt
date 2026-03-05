import os
import unittest
from tempfile import TemporaryDirectory
from unittest import mock

from novaadapt_core.voice import (
    NoopSTTBackend,
    NoopTTSBackend,
    StaticSTTBackend,
    StaticTTSBackend,
    TalkModeSession,
    build_stt_backend,
    build_tts_backend,
    build_wake_detector,
)


class VoiceTests(unittest.TestCase):
    def test_noop_backends_report_not_configured(self):
        stt = NoopSTTBackend()
        tts = NoopTTSBackend()
        transcribed = stt.transcribe("/tmp/a.wav")
        spoken = tts.synthesize("hello")

        self.assertFalse(transcribed.ok)
        self.assertIn("not configured", str(transcribed.error))
        self.assertFalse(spoken.ok)
        self.assertIn("not configured", str(spoken.error))

    def test_wake_detector_matches_phrase_case_insensitive(self):
        detector = build_wake_detector(["Hey Nova"])
        signal = detector.detect("please HEY    nova open the map", confidence=0.9)
        self.assertTrue(signal.detected)
        self.assertEqual(signal.phrase, "Hey Nova")

    def test_wake_detector_requires_min_confidence(self):
        detector = build_wake_detector(["hey nova"], min_confidence=0.8)
        signal = detector.detect("hey nova", confidence=0.5)
        self.assertFalse(signal.detected)

    def test_talk_mode_ignores_turn_without_wake_phrase(self):
        session = TalkModeSession(
            stt=StaticSTTBackend(text="just checking status"),
            tts=StaticTTSBackend(),
            objective_runner=lambda objective: objective,
            wake_detector=build_wake_detector(["hey nova"]),
            require_wake_word=True,
        )
        out = session.handle_audio("/tmp/in.wav")
        self.assertTrue(out.ok)
        self.assertFalse(out.triggered)
        self.assertIsNone(out.synthesis)

    def test_talk_mode_runs_objective_and_synthesizes(self):
        with TemporaryDirectory() as tmp:
            session = TalkModeSession(
                stt=StaticSTTBackend(text="hey nova plot a route"),
                tts=StaticTTSBackend(),
                objective_runner=lambda objective: f"Roger: {objective}",
                wake_detector=build_wake_detector(["hey nova"]),
                require_wake_word=True,
            )
            output_path = os.path.join(tmp, "reply.txt")
            out = session.handle_audio("/tmp/in.wav", output_path=output_path)
            self.assertTrue(out.ok)
            self.assertTrue(out.triggered)
            self.assertTrue(out.wake.detected)
            self.assertEqual(out.response_text, "Roger: hey nova plot a route")
            self.assertIsNotNone(out.synthesis)
            assert out.synthesis is not None
            self.assertEqual(out.synthesis.output_path, output_path)
            self.assertTrue(os.path.exists(output_path))

    def test_backend_factories_support_static_env_mode(self):
        with mock.patch.dict(
            os.environ,
            {
                "NOVAADAPT_STT_BACKEND": "static",
                "NOVAADAPT_STT_STATIC_TEXT": "sample",
                "NOVAADAPT_TTS_BACKEND": "static",
            },
            clear=False,
        ):
            stt = build_stt_backend()
            tts = build_tts_backend()

        self.assertIsInstance(stt, StaticSTTBackend)
        self.assertIsInstance(tts, StaticTTSBackend)


if __name__ == "__main__":
    unittest.main()
