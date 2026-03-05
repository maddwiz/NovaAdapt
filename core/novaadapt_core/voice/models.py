from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranscriptionResult:
    ok: bool
    text: str = ""
    backend: str = ""
    confidence: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SynthesisResult:
    ok: bool
    backend: str = ""
    output_path: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WakeSignal:
    detected: bool
    phrase: str = ""
    transcript: str = ""
    confidence: float = 0.0
