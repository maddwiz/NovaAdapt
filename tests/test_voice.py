import os
import unittest
from tempfile import TemporaryDirectory
from unittest import mock

from novaadapt_core.voice import (
    CommandSTTBackend,
    CommandTTSBackend,
    NoopSTTBackend,
    NoopTTSBackend,
    OpenAISTTBackend,
    OpenAITTSBackend,
    StaticSTTBackend,
    StaticTTSBackend,
    TalkModeSession,
    build_stt_backend,
    build_tts_backend,
    build_wake_detector,
)


class _DummyHTTPResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


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

    def test_command_stt_backend_returns_stdout_text(self):
        backend = CommandSTTBackend(command="echo test")
        completed = mock.Mock(returncode=0, stdout='{"text":"route clear","confidence":0.73}', stderr="")
        with mock.patch("novaadapt_core.voice.stt.subprocess.run", return_value=completed):
            out = backend.transcribe("/tmp/input.wav", hints=["map"])
        self.assertTrue(out.ok)
        self.assertEqual(out.text, "route clear")
        self.assertAlmostEqual(float(out.confidence or 0.0), 0.73, places=2)

    def test_command_tts_backend_writes_stdout_when_file_missing(self):
        backend = CommandTTSBackend(command="echo hi")
        completed = mock.Mock(returncode=0, stdout=b"audio-bytes", stderr=b"")
        with TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "speech.bin")
            with mock.patch("novaadapt_core.voice.tts.subprocess.run", return_value=completed):
                out = backend.synthesize("hello", output_path=output_path, voice="alloy")
            self.assertTrue(out.ok)
            self.assertEqual(out.output_path, output_path)
            with open(output_path, "rb") as fh:
                self.assertEqual(fh.read(), b"audio-bytes")

    def test_openai_stt_backend_parses_json_response(self):
        with TemporaryDirectory() as tmp:
            audio_path = os.path.join(tmp, "input.wav")
            with open(audio_path, "wb") as fh:
                fh.write(b"audio")
            backend = OpenAISTTBackend()
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=False):
                with mock.patch(
                    "novaadapt_core.voice.stt.request.urlopen",
                    return_value=_DummyHTTPResponse(b'{"text":"hello world","confidence":0.91}'),
                ):
                    out = backend.transcribe(audio_path, hints=["help"])
            self.assertTrue(out.ok)
            self.assertEqual(out.text, "hello world")
            self.assertAlmostEqual(float(out.confidence or 0.0), 0.91, places=2)

    def test_openai_tts_backend_writes_audio_blob(self):
        backend = OpenAITTSBackend(audio_format="mp3")
        with TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "speech.mp3")
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=False):
                with mock.patch(
                    "novaadapt_core.voice.tts.request.urlopen",
                    return_value=_DummyHTTPResponse(b"\x00\x01\x02"),
                ):
                    out = backend.synthesize("hello", output_path=output_path, voice="nova")
            self.assertTrue(out.ok)
            self.assertEqual(out.output_path, output_path)
            with open(output_path, "rb") as fh:
                self.assertEqual(fh.read(), b"\x00\x01\x02")

    def test_openai_backends_fail_without_api_key(self):
        stt = OpenAISTTBackend()
        tts = OpenAITTSBackend()
        with mock.patch.dict(os.environ, {}, clear=True):
            stt_out = stt.transcribe("/tmp/missing.wav")
            tts_out = tts.synthesize("hello")
        self.assertFalse(stt_out.ok)
        self.assertIn("missing API key", str(stt_out.error))
        self.assertFalse(tts_out.ok)
        self.assertIn("missing API key", str(tts_out.error))

    def test_stt_factory_supports_command_and_openai_modes(self):
        with mock.patch.dict(
            os.environ,
            {
                "NOVAADAPT_STT_BACKEND": "command",
                "NOVAADAPT_STT_COMMAND": "echo test",
            },
            clear=False,
        ):
            cmd_backend = build_stt_backend()
        self.assertIsInstance(cmd_backend, CommandSTTBackend)

        with mock.patch.dict(
            os.environ,
            {
                "NOVAADAPT_STT_BACKEND": "openai",
                "NOVAADAPT_STT_OPENAI_MODEL": "gpt-4o-mini-transcribe",
            },
            clear=False,
        ):
            openai_backend = build_stt_backend()
        self.assertIsInstance(openai_backend, OpenAISTTBackend)

    def test_tts_factory_supports_command_and_openai_modes(self):
        with mock.patch.dict(
            os.environ,
            {
                "NOVAADAPT_TTS_BACKEND": "command",
                "NOVAADAPT_TTS_COMMAND": "echo test",
            },
            clear=False,
        ):
            cmd_backend = build_tts_backend()
        self.assertIsInstance(cmd_backend, CommandTTSBackend)

        with mock.patch.dict(
            os.environ,
            {
                "NOVAADAPT_TTS_BACKEND": "openai",
                "NOVAADAPT_TTS_OPENAI_MODEL": "gpt-4o-mini-tts",
            },
            clear=False,
        ):
            openai_backend = build_tts_backend()
        self.assertIsInstance(openai_backend, OpenAITTSBackend)


if __name__ == "__main__":
    unittest.main()
