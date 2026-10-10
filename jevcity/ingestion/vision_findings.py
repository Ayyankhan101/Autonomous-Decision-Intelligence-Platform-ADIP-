"""Vision evidence → soft validation findings. Evidence, not authority: this is
the ONLY lever vision has into policy (spec: no severity writes, no ML triad)."""
from __future__ import annotations

from jevcity.schemas import (
    DamageSeverity,
    IncidentRecord,
    SeverityHint,
    ValidationFinding,
    VisionFacts,
    VisionStatus,
)

_RANK = {SeverityHint.MINOR: 0, SeverityHint.MODERATE: 1, SeverityHint.SEVERE: 2}
_DAMAGE_RANK = {DamageSeverity.LOW: 0, DamageSeverity.MEDIUM: 1,
                DamageSeverity.HIGH: 2}


def vision_findings(facts: VisionFacts, incident: IncidentRecord) -> list[ValidationFinding]:
    if facts.status is not VisionStatus.OK:
        return []
    if incident.severity_hint is None or facts.damage_severity is DamageSeverity.UNKNOWN:
        return []
    gap = _DAMAGE_RANK[facts.damage_severity] - _RANK.get(incident.severity_hint, 1)
    if gap >= 2:
        return [ValidationFinding(
            severity="soft", code="severity_mismatch_vision",
            message=(f"vision damage={facts.damage_severity.value} vs reported "
                     f"severity={incident.severity_hint.value} (evidence only)"),
        )]
    return []
