"""Feature engineering (plan §5.2): simulated-time features only, no host wall-clock."""
from __future__ import annotations

from jevcity.schemas import EventEnvelope
from jevcity.simulation.clock import SimClock


def build_features(reports: list[EventEnvelope]) -> dict:
    if not reports:
        raise ValueError("no reports for feature build")
    primary = sorted(reports, key=lambda e: e.simulated_time)[0]
    ctx = primary.context
    attrs = primary.reported_attributes
    when = primary.simulated_time
    return {
        "incident_type": primary.incident_type.value,
        "zone": primary.location.zone.value,
        "hour": when.hour,
        "time_of_day_bucket": SimClock.time_of_day_bucket(when),
        "weather": ctx.weather,
        "traffic_level": ctx.traffic_level,
        "severity_hint": attrs.severity.value if attrs.severity else None,
        "vehicles_involved": attrs.vehicles_involved,
        "injuries_reported": attrs.injuries_reported,
        "lanes_blocked": attrs.lanes_blocked,
        "report_count": len(reports),
    }
