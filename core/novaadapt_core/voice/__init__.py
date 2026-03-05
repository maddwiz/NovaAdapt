from __future__ import annotations

"""Optional voice interfaces for NovaAdapt (standalone-safe)."""

from .models import SynthesisResult, TranscriptionResult, WakeSignal
from .stt import (
    CommandSTTBackend,
    NoopSTTBackend,
    OpenAISTTBackend,
    SpeechToTextBackend,
    StaticSTTBackend,
    build_stt_backend,
)
from .talk_mode import TalkModeSession, TalkTurnResult
from .tts import (
    CommandTTSBackend,
    NoopTTSBackend,
    OpenAITTSBackend,
    StaticTTSBackend,
    TextToSpeechBackend,
    build_tts_backend,
)
from .wake import KeywordWakeDetector, build_wake_detector

__all__ = [
    "CommandSTTBackend",
    "CommandTTSBackend",
    "KeywordWakeDetector",
    "NoopSTTBackend",
    "NoopTTSBackend",
    "OpenAISTTBackend",
    "OpenAITTSBackend",
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
