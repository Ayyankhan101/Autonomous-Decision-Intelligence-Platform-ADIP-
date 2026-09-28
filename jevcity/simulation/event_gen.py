"""Controlled event generator (plan Phase 1): seeded severity randomization, multi-report
correlation keys, bounded adversarial free-text fields."""
from __future__ import annotations

import random
from datetime import datetime

from jevcity.schemas import (
    EventContext,
    EventEnvelope,
    IncidentType,
    Location,
    QualityHints,
    ReportedAttributes,
    SeverityHint,
    Zone,
)

_WEATHER = ["clear", "rain", "snow", "fog"]
_TRAFFIC = ["free_flow", "moderate", "high", "gridlock"]

_SEVERITY_RANK = [SeverityHint.MINOR, SeverityHint.MODERATE, SeverityHint.SEVERE]


class EventGenerator:
    def __init__(self, session_rng: random.Random, scenario_rng: random.Random) -> None:
        self.session_rng = session_rng
        self.scenario_rng = scenario_rng
        self._event_counter = 0
        self._incident_counter = 0

    def next_incident_id(self) -> str:
        self._incident_counter += 1
        return f"inc-{self._incident_counter:05d}"

    def next_event_id(self) -> str:
        self._event_counter += 1
        return f"evt-{self._event_counter:06d}"

    def make_incident(
        self,
        incident_type: IncidentType,
        zone: Zone,
        severity: SeverityHint | None = None,
        *,
        source_id: str = "sensor-auto-01",
        when: datetime | None = None,
        incident_id: str | None = None,
        notes: str | None = None,
        severity_jitter: bool = True,
    ) -> EventEnvelope:
        if when is None:
            raise ValueError("when (simulated time) is required — never use wall clock")
        chosen = severity or self._random_severity(jitter=severity_jitter)
        attributes = self._attributes_for(incident_type, chosen)
        if notes is not None:
            attributes.notes = notes
        return EventEnvelope(
            event_id=self.next_event_id(),
            incident_id=incident_id or self.next_incident_id(),
            source_id=source_id,
            incident_type=incident_type,
            simulated_time=when,
            ingest_time=when,
            location=Location(
                zone=zone,
                lat=round(51.50 + self.session_rng.uniform(-0.05, 0.05), 3),
                lon=round(-0.14 + self.session_rng.uniform(-0.05, 0.05), 3),
                road_segment_id=f"rs-{self.session_rng.randint(1, 99):02d}",
            ),
            reported_attributes=attributes,
            context=self._context(when),
            quality_hints=QualityHints(),
        )

    def second_report(
        self, first: EventEnvelope, *, when: datetime, source_id: str, contradict: bool = True
    ) -> EventEnvelope:
        """Second observation of the same incident (incident_id correlation). When
        contradict=True, inject a conflicting severity report."""
        attrs = first.reported_attributes.model_copy(deep=True)
        if contradict:
            current = attrs.severity or SeverityHint.MINOR
            idx = _SEVERITY_RANK.index(current)
            attrs.severity = _SEVERITY_RANK[min(idx + 1, len(_SEVERITY_RANK) - 1)]
            attrs.injuries_reported = (attrs.injuries_reported or 0) + 1
        return first.model_copy(
            update={
                "event_id": self.next_event_id(),
                "source_id": source_id,
                "simulated_time": when,
                "ingest_time": when,
                "reported_attributes": attrs,
                "quality_hints": QualityHints(),
            }
        )

    def _random_severity(self, *, jitter: bool) -> SeverityHint:
        if not jitter:
            return SeverityHint.MODERATE
        return self.session_rng.choice(_SEVERITY_RANK)

    @staticmethod
    def _attributes_for(incident_type: IncidentType, severity: SeverityHint) -> ReportedAttributes:
        base = {
            SeverityHint.MINOR: dict(vehicles_involved=1, injuries_reported=0, lanes_blocked=1),
            SeverityHint.MODERATE: dict(vehicles_involved=2, injuries_reported=1, lanes_blocked=1),
            SeverityHint.SEVERE: dict(vehicles_involved=4, injuries_reported=3, lanes_blocked=2),
        }[severity]
        if incident_type == IncidentType.FLOOD:
            base = dict(vehicles_involved=0, injuries_reported=0, lanes_blocked=2)
        elif incident_type == IncidentType.FIRE:
            base = dict(vehicles_involved=0, injuries_reported=1, lanes_blocked=1)
        return ReportedAttributes(severity=severity, **base)

    def _context(self, when: datetime) -> EventContext:
        return EventContext(
            weather=self.session_rng.choice(_WEATHER),
            traffic_level=self.session_rng.choice(_TRAFFIC),
            time_of_day_bucket=None,
        )
