from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from .models import TranscriptionResult


class SpeechToTextBackend(Protocol):
    name: str

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult: ...


@dataclass
class NoopSTTBackend:
    name: str = "noop-stt"

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            ok=False,
            backend=self.name,
            error="stt backend not configured",
            metadata={
                "audio_path": str(audio_path),
                "hints": list(hints or []),
                **dict(metadata or {}),
            },
        )


@dataclass
class StaticSTTBackend:
    text: str
    confidence: float = 1.0
    name: str = "static-stt"

    def transcribe(
        self,
        audio_path: str,
        *,
        hints: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        return TranscriptionResult(
            ok=True,
            text=str(self.text),
            backend=self.name,
            confidence=max(0.0, min(1.0, float(self.confidence))),
            metadata={
                "audio_path": str(audio_path),
                "hints": list(hints or []),
                **dict(metadata or {}),
            },
        )


def build_stt_backend(kind: str | None = None) -> SpeechToTextBackend:
    backend_kind = str(kind or os.getenv("NOVAADAPT_STT_BACKEND", "noop")).strip().lower()
    if backend_kind in {"", "noop", "none"}:
        return NoopSTTBackend()
    if backend_kind == "static":
        text = str(os.getenv("NOVAADAPT_STT_STATIC_TEXT", "")).strip()
        confidence_raw = str(os.getenv("NOVAADAPT_STT_STATIC_CONFIDENCE", "1.0")).strip() or "1.0"
        try:
            confidence = float(confidence_raw)
        except ValueError:
            confidence = 1.0
        return StaticSTTBackend(text=text, confidence=confidence)
    raise ValueError(f"unsupported STT backend: {backend_kind}")
