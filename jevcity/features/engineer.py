"""Feature engineering (plan §5.2): simulated-time features only, no host wall-clock."""
from __future__ import annotations

from jevcity.schemas import EventEnvelope
from jevcity.simulation.clock import SimClock


def build_features(reports: list[EventEnvelope], *, history: dict | None = None) -> dict:
    if not reports:
        raise ValueError("no reports for feature build")
    primary = sorted(reports, key=lambda e: e.simulated_time)[0]
    ctx = primary.context
    attrs = primary.reported_attributes
    when = primary.simulated_time
    hist = history or {}
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
        "zone_share": float(hist.get("zone_share", 0.0)),
        "type_share": float(hist.get("type_share", 0.0)),
    }


def history_features(
    incidents: dict,
    zone: str,
    incident_type: str,
    *,
    exclude_id: str | None = None,
) -> dict:
    prior = [inc for key, inc in incidents.items() if key != exclude_id]
    if not prior:
        return {"zone_share": 0.0, "type_share": 0.0}
    zone_hits = sum(1 for inc in prior if inc.zone.value == zone)
    type_hits = sum(1 for inc in prior if inc.incident_type.value == incident_type)
    return {"zone_share": zone_hits / len(prior), "type_share": type_hits / len(prior)}
