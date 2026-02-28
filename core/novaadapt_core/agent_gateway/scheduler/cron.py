from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CronJob:
    name: str
    payload: dict[str, Any]
    interval_seconds: int
    next_run_at: datetime = field(default_factory=_utc_now)


class CronScheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, CronJob] = {}

    def register(self, name: str, payload: dict[str, Any], *, interval_seconds: int) -> None:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("name is required")
        if int(interval_seconds) <= 0:
            raise ValueError("interval_seconds must be > 0")
        self._jobs[normalized_name] = CronJob(
            name=normalized_name,
            payload=dict(payload if isinstance(payload, dict) else {}),
            interval_seconds=max(1, int(interval_seconds)),
            next_run_at=_utc_now(),
        )

    def due(self, *, now: datetime | None = None) -> list[CronJob]:
        current = now or _utc_now()
        out: list[CronJob] = []
        for item in self._jobs.values():
            if item.next_run_at <= current:
                out.append(item)
        return out

    def mark_ran(self, name: str, *, now: datetime | None = None) -> None:
        item = self._jobs.get(str(name or "").strip())
        if item is None:
            return
        current = now or _utc_now()
        item.next_run_at = current + timedelta(seconds=item.interval_seconds)
