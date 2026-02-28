from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HeartbeatScheduler:
    def __init__(self, interval_seconds: int = 1800) -> None:
        self.interval_seconds = max(1, int(interval_seconds))
        self._next = _utc_now()

    def due(self, *, now: datetime | None = None) -> bool:
        current = now or _utc_now()
        return current >= self._next

    def mark_beat(self, *, now: datetime | None = None) -> None:
        current = now or _utc_now()
        self._next = current + timedelta(seconds=self.interval_seconds)
