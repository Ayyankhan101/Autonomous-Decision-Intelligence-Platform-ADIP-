"""Simulated clock (plan Phase 1): all timestamps come from here, never host wall-clock."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

EPOCH = datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)


class SimClock:
    def __init__(self, start: datetime = EPOCH, step_seconds: int = 1) -> None:
        self._now = start
        self._step = timedelta(seconds=step_seconds)

    @property
    def now(self) -> datetime:
        return self._now

    def tick(self) -> datetime:
        self._now += self._step
        return self._now

    def advance(self, seconds: int) -> datetime:
        self._now += timedelta(seconds=seconds)
        return self._now

    def reset(self, start: datetime = EPOCH) -> None:
        self._now = start

    @staticmethod
    def time_of_day_bucket(when: datetime) -> str:
        hour = when.hour
        if 7 <= hour < 10:
            return "morning_peak"
        if 16 <= hour < 19:
            return "evening_peak"
        if 6 <= hour < 22:
            return "day"
        return "night"
