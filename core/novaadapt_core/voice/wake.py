from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable

from .models import WakeSignal


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


@dataclass
class KeywordWakeDetector:
    phrases: tuple[str, ...] = field(default_factory=lambda: ("hey nova",))
    min_confidence: float = 0.5

    def detect(self, transcript: str, *, confidence: float = 1.0) -> WakeSignal:
        cleaned = _normalize(transcript)
        conf = max(0.0, min(1.0, float(confidence)))
        if conf < self.min_confidence:
            return WakeSignal(detected=False, phrase="", transcript=str(transcript or ""), confidence=conf)
        for phrase in self.phrases:
            candidate = _normalize(phrase)
            if candidate and candidate in cleaned:
                return WakeSignal(
                    detected=True,
                    phrase=phrase,
                    transcript=str(transcript or ""),
                    confidence=conf,
                )
        return WakeSignal(detected=False, phrase="", transcript=str(transcript or ""), confidence=conf)


def build_wake_detector(
    phrases: Iterable[str] | None = None,
    *,
    min_confidence: float | None = None,
) -> KeywordWakeDetector:
    if phrases is None:
        raw = str(os.getenv("NOVAADAPT_WAKE_PHRASES", "")).strip()
        if raw:
            phrases = [item.strip() for item in raw.split(",") if item.strip()]
        else:
            phrases = ("hey nova",)
    parsed = tuple(item for item in (str(p).strip() for p in phrases) if item)
    threshold_raw = (
        str(min_confidence)
        if min_confidence is not None
        else str(os.getenv("NOVAADAPT_WAKE_MIN_CONFIDENCE", "0.5")).strip()
    )
    try:
        threshold = float(threshold_raw)
    except ValueError:
        threshold = 0.5
    return KeywordWakeDetector(phrases=parsed or ("hey nova",), min_confidence=max(0.0, min(1.0, threshold)))
