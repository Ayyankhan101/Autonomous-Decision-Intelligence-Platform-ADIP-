"""Multi-report correlation by incident_id + contradiction detection (plan §3, Phase 1)."""
from __future__ import annotations

from dataclasses import dataclass, field

from jevcity.schemas import EventEnvelope


@dataclass
class CorrelationResult:
    incident_id: str
    report_count: int
    contradictions: list[str] = field(default_factory=list)

    @property
    def has_contradiction(self) -> bool:
        return bool(self.contradictions)


def correlate(reports: list[EventEnvelope]) -> CorrelationResult:
    if not reports:
        raise ValueError("no reports to correlate")
    incident_id = reports[0].incident_id
    contradictions: list[str] = []
    severities = {r.reported_attributes.severity for r in reports if r.reported_attributes.severity}
    if len(severities) > 1:
        contradictions.append("contradictory_reports")
    zones = {r.location.zone for r in reports}
    if len(zones) > 1:
        contradictions.append("conflicting_location")
    injuries = {
        r.reported_attributes.injuries_reported
        for r in reports
        if r.reported_attributes.injuries_reported is not None
    }
    if len(injuries) > 1:
        contradictions.append("conflicting_injury_count")
    roads = {r.location.road_segment_id for r in reports}
    if len(roads) > 1:
        contradictions.append("conflicting_road_segment")
    return CorrelationResult(
        incident_id=incident_id, report_count=len(reports), contradictions=contradictions
    )
