from __future__ import annotations

"""Optional voice interfaces for NovaAdapt (standalone-safe)."""

from .models import SynthesisResult, TranscriptionResult, WakeSignal
from .stt import NoopSTTBackend, SpeechToTextBackend, StaticSTTBackend, build_stt_backend
from .talk_mode import TalkModeSession, TalkTurnResult
from .tts import NoopTTSBackend, StaticTTSBackend, TextToSpeechBackend, build_tts_backend
from .wake import KeywordWakeDetector, build_wake_detector

__all__ = [
    "KeywordWakeDetector",
    "NoopSTTBackend",
    "NoopTTSBackend",
    "SpeechToTextBackend",
    "StaticSTTBackend",
    "StaticTTSBackend",
    "SynthesisResult",
    "TalkModeSession",
    "TalkTurnResult",
    "TextToSpeechBackend",
    "TranscriptionResult",
    "WakeSignal",
    "build_stt_backend",
    "build_tts_backend",
    "build_wake_detector",
]
