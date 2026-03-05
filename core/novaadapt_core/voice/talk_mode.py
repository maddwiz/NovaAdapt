from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .models import SynthesisResult, TranscriptionResult, WakeSignal
from .stt import SpeechToTextBackend
from .tts import TextToSpeechBackend
from .wake import KeywordWakeDetector


@dataclass(frozen=True)
class TalkTurnResult:
    ok: bool
    active: bool
    triggered: bool
    transcript: TranscriptionResult
    wake: WakeSignal
    response_text: str = ""
    synthesis: SynthesisResult | None = None
    error: str | None = None


class TalkModeSession:
    def __init__(
        self,
        *,
        stt: SpeechToTextBackend,
        tts: TextToSpeechBackend,
        objective_runner: Callable[[str], str] | None = None,
        wake_detector: KeywordWakeDetector | None = None,
        require_wake_word: bool = True,
    ) -> None:
        self._stt = stt
        self._tts = tts
        self._objective_runner = objective_runner
        self._wake_detector = wake_detector
        self._require_wake_word = bool(require_wake_word)
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def activate(self) -> None:
        self._active = True

    def deactivate(self) -> None:
        self._active = False

    def handle_audio(
        self,
        audio_path: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> TalkTurnResult:
        transcription = self._stt.transcribe(audio_path, metadata=metadata)
        if not transcription.ok:
            return TalkTurnResult(
                ok=False,
                active=self._active,
                triggered=False,
                transcript=transcription,
                wake=WakeSignal(detected=False, transcript=transcription.text, confidence=0.0),
                error=transcription.error or "stt_failed",
            )

        wake = WakeSignal(detected=True, phrase="", transcript=transcription.text, confidence=1.0)
        if self._wake_detector is not None:
            wake = self._wake_detector.detect(
                transcription.text,
                confidence=float(transcription.confidence or 1.0),
            )
            if self._require_wake_word and not wake.detected:
                return TalkTurnResult(
                    ok=True,
                    active=self._active,
                    triggered=False,
                    transcript=transcription,
                    wake=wake,
                )

        if self._objective_runner is None:
            return TalkTurnResult(
                ok=True,
                active=self._active,
                triggered=True,
                transcript=transcription,
                wake=wake,
            )

        response_text = str(self._objective_runner(transcription.text))
        synthesis = self._tts.synthesize(
            response_text,
            output_path=output_path,
            voice=voice,
            metadata=metadata,
        )
        return TalkTurnResult(
            ok=synthesis.ok,
            active=self._active,
            triggered=True,
            transcript=transcription,
            wake=wake,
            response_text=response_text,
            synthesis=synthesis,
            error=(None if synthesis.ok else (synthesis.error or "tts_failed")),
        )
