from __future__ import annotations

from collections import defaultdict, deque

from .renderer import CanvasRenderResult


class CanvasSessionStore:
    def __init__(self, *, max_frames_per_session: int = 100) -> None:
        self.max_frames_per_session = max(1, int(max_frames_per_session))
        self._sessions: dict[str, deque[CanvasRenderResult]] = defaultdict(
            lambda: deque(maxlen=self.max_frames_per_session)
        )

    def push(self, session_id: str, frame: CanvasRenderResult) -> CanvasRenderResult:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("'session_id' is required")
        self._sessions[normalized].append(frame)
        return frame

    def latest(self, session_id: str) -> CanvasRenderResult | None:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("'session_id' is required")
        frames = self._sessions.get(normalized)
        if not frames:
            return None
        return frames[-1]

    def list(self, session_id: str, *, limit: int = 20) -> list[CanvasRenderResult]:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("'session_id' is required")
        frames = self._sessions.get(normalized)
        if not frames:
            return []
        capped = max(1, min(200, int(limit)))
        return list(frames)[-capped:]

    def clear(self, session_id: str) -> int:
        normalized = str(session_id or "").strip()
        if not normalized:
            raise ValueError("'session_id' is required")
        frames = self._sessions.pop(normalized, None)
        return len(frames or [])
