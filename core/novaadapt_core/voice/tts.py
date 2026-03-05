from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import SynthesisResult


class TextToSpeechBackend(Protocol):
    name: str

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult: ...


@dataclass
class NoopTTSBackend:
    name: str = "noop-tts"

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        return SynthesisResult(
            ok=False,
            backend=self.name,
            error="tts backend not configured",
            output_path=str(output_path or ""),
            metadata={
                "voice": str(voice or ""),
                "text_length": len(str(text or "")),
                **dict(metadata or {}),
            },
        )


@dataclass
class StaticTTSBackend:
    name: str = "static-tts"

    def synthesize(
        self,
        text: str,
        *,
        output_path: str = "",
        voice: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        out = Path(output_path or "").expanduser()
        if not str(out):
            out = Path.cwd() / "novaadapt_voice_output.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(str(text), encoding="utf-8")
        return SynthesisResult(
            ok=True,
            backend=self.name,
            output_path=str(out),
            metadata={
                "voice": str(voice or ""),
                "text_length": len(str(text or "")),
                **dict(metadata or {}),
            },
        )


def build_tts_backend(kind: str | None = None) -> TextToSpeechBackend:
    backend_kind = str(kind or os.getenv("NOVAADAPT_TTS_BACKEND", "noop")).strip().lower()
    if backend_kind in {"", "noop", "none"}:
        return NoopTTSBackend()
    if backend_kind == "static":
        return StaticTTSBackend()
    raise ValueError(f"unsupported TTS backend: {backend_kind}")
