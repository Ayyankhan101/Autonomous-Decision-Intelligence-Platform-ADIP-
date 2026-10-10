"""Per-stream veracity + availability trust scoring (enhancement 1).

Rule-based extension of the anomaly-detection component. Veracity falls when a source
disagrees with the primary observation, exceeds a report-rate burst, or arrives inside a
Sybil cluster (many novel identities on one incident). Scores recover gradually on clean
corroborating reports — transient anomalies never permanently blacklist a stream."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from jevcity.schemas import EventEnvelope, TrustBlock

FLAG_THRESHOLD = 0.6
TRUST_GATE = 0.7
CONTRADICTION_PENALTY = 0.25
SYBIL_DISAGREE_PENALTY = 0.45
RATE_PENALTY = 0.4
RECOVERY_GAIN = 0.05
AVAILABILITY_DECAY = 0.08
AVAILABILITY_RECOVERY = 0.05
RATE_WINDOW_SECONDS = 120
RATE_LIMIT = 3
SYBIL_CLUSTER_MIN = 4


class TrustRegistry:
    """Rule-based per-source trust keyed by EventEnvelope.source_id (sidecar — no
    frozen-schema changes). observe() is idempotent per event_id, so re-optimisation
    and replay never double-penalise."""

    def __init__(self) -> None:
        self.veracity: dict[str, float] = {}
        self.availability: dict[str, float] = {}
        self._ever_seen: set[str] = set()
        self._observed_events: set[str] = set()
        self._recent_times: dict[str, list[datetime]] = defaultdict(list)

    def observe(self, reports: list[EventEnvelope]) -> None:
        if not reports:
            return
        primary = min(reports, key=lambda e: e.simulated_time)
        primary_sev = primary.reported_attributes.severity
        present = {r.source_id for r in reports}
        new_in_batch = present - self._ever_seen
        cluster = len(new_in_batch) >= SYBIL_CLUSTER_MIN

        for report in reports:
            if report.event_id in self._observed_events:
                continue
            self._observed_events.add(report.event_id)
            src = report.source_id
            times = self._recent_times[src]
            times.append(report.simulated_time)
            window = [
                t for t in times if (report.simulated_time - t).total_seconds() <= RATE_WINDOW_SECONDS
            ]
            self._recent_times[src] = window

            if src not in self.veracity:
                self.veracity[src] = 1.0
                self.availability[src] = 1.0

            disagrees = (
                primary_sev is not None
                and report.reported_attributes.severity != primary_sev
                and report.event_id != primary.event_id
            )
            if len(window) > RATE_LIMIT:
                self.veracity[src] = max(0.0, self.veracity[src] - RATE_PENALTY)
            elif disagrees and cluster and src in new_in_batch:
                self.veracity[src] = max(0.0, self.veracity[src] - SYBIL_DISAGREE_PENALTY)
            elif disagrees:
                self.veracity[src] = max(0.0, self.veracity[src] - CONTRADICTION_PENALTY)
            else:
                self.veracity[src] = min(1.0, self.veracity[src] + RECOVERY_GAIN)

        for src in list(self.veracity.keys()):
            if src in present:
                self.availability[src] = min(1.0, self.availability[src] + AVAILABILITY_RECOVERY)
            else:
                self.availability[src] = max(0.0, self.availability[src] - AVAILABILITY_DECAY)
        self._ever_seen |= present

    def flagged(self) -> list[str]:
        return sorted(s for s, v in self.veracity.items() if v < FLAG_THRESHOLD)

    def mean_veracity(self, source_ids: list[str]) -> float:
        if not source_ids:
            return 1.0
        return sum(self.veracity.get(s, 1.0) for s in source_ids) / len(source_ids)

    def block_for(self, source_ids: list[str]) -> TrustBlock:
        scores = {s: round(self.veracity.get(s, 1.0), 3) for s in source_ids}
        flagged = [s for s in source_ids if self.veracity.get(s, 1.0) < FLAG_THRESHOLD]
        avail = {s: round(self.availability.get(s, 1.0), 3) for s in source_ids}
        return TrustBlock(
            source_scores=scores,
            mean_veracity=round(sum(scores.values()) / len(scores), 3) if scores else 1.0,
            flagged_sources=flagged,
            availability=avail,
        )
