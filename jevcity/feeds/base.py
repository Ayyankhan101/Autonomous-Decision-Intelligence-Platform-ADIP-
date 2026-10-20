"""Live environmental feed manager (workstream B1).

Each feed is a poller hitting a free, no-key public API on a daemon thread.
Feeds append `EventEnvelope`s into `SimulationState.append_replay`; the engine's
`process_pending()` then decides on them exactly as it does simulated events.
Circuit-breaker mirrors the laya adapter: after N consecutive failures a feed is
held open for a probe period so a dead upstream cannot spin the daemon.
"""
from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import httpx

from jevcity.schemas import EventEnvelope, FeedStatus

CIRCUIT_BREAKER_THRESHOLD = 3
PROBE_INTERVAL_S = 300.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km, shared by the geo-filtering feeds."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class FeedError(RuntimeError):
    """Raised by a poller when the upstream call fails or returns bad data."""


class FeedPoller(Protocol):
    name: str

    def poll(self) -> list[EventEnvelope]:
        """Return zero or more events. Raise FeedError on upstream failure."""
        ...


@dataclass
class FeedHealth:
    name: str
    ok: bool = False
    last_poll: datetime | None = None
    consecutive_failures: int = 0
    events_last_poll: int = 0
    total_events: int = 0
    detail: str | None = None
    _held_until: float = field(default=0.0, repr=False)

    def held_open(self) -> bool:
        return time.monotonic() < self._held_until

    def record_success(self, event_count: int, when: datetime) -> None:
        self.ok = True
        self.last_poll = when
        self.consecutive_failures = 0
        self.events_last_poll = event_count
        self.total_events += event_count
        self.detail = None
        self._held_until = 0.0

    def record_failure(self, detail: str) -> None:
        self.ok = False
        self.consecutive_failures += 1
        self.detail = detail
        self.events_last_poll = 0
        if self.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            self._held_until = time.monotonic() + PROBE_INTERVAL_S

    def snapshot(self) -> FeedStatus:
        return FeedStatus(
            name=self.name,
            ok=self.ok,
            last_poll=self.last_poll,
            consecutive_failures=self.consecutive_failures,
            events_last_poll=self.events_last_poll,
            total_events=self.total_events,
            detail=self.detail,
        )


class FeedManager:
    """Daemon thread cycling every feed, jittered. Owns health per feed."""

    def __init__(
        self,
        pollers: list[FeedPoller],
        target,
        cycle_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.pollers = pollers
        self.target = target
        self.cycle_seconds = cycle_seconds
        self._client = client or httpx.Client(timeout=10.0)
        self._health: dict[str, FeedHealth] = {
            p.name: FeedHealth(name=p.name) for p in pollers
        }
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="feed-manager"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def poll_once(self) -> tuple[int, int]:
        """Run one cycle synchronously. Returns (events_ingested, feed_errors)."""
        ingested = 0
        errors = 0
        for poller in self.pollers:
            health = self._health[poller.name]
            if health.held_open():
                continue
            try:
                events = poller.poll()
            except Exception as exc:  # noqa: BLE001 — one dead feed must not kill the cycle
                health.record_failure(str(exc))
                errors += 1
                continue
            health.record_success(len(events), datetime.now(timezone.utc))
            for event in events:
                try:
                    self.target.append_replay(event)
                    ingested += 1
                except Exception:  # noqa: BLE001 — a malformed event is one failure, not a crash
                    health.record_failure(f"append_replay rejected: {event.event_id}")
                    errors += 1
        return ingested, errors

    def snapshots(self) -> list[FeedStatus]:
        return [self._health[p.name].snapshot() for p in self.pollers]

    def health(self, name: str) -> FeedHealth | None:
        return self._health.get(name)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            jitter = random.uniform(0.8, 1.2)
            self._stop.wait(self.cycle_seconds * jitter)
