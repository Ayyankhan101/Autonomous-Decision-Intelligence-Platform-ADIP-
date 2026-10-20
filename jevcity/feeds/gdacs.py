"""GDACS alert feed (free, no API key). Flood + earthquake, orange/red only.

Maps to the frozen IncidentType enum: FL → flood, EQ → traffic_spike (same honest
mapping as the USGS feed). Distance filter keeps only alerts near Peshawar.
"""
from __future__ import annotations

from datetime import datetime, timezone

from jevcity.schemas import (
    EventEnvelope,
    IncidentType,
    Location,
    QualityHints,
    ReportedAttributes,
    SeverityHint,
    Zone,
)

from .base import FeedError, haversine_km

URL = (
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    "?eventlist=FL;EQ&alertlevel=orange;red"
)
CENTER = (34.008, 71.578)
MAX_DISTANCE_KM = 300.0


class GdacsFeed:
    name = "gdacs"

    def __init__(self, client) -> None:
        self._client = client

    def poll(self) -> list[EventEnvelope]:
        try:
            resp = self._client.get(URL)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise FeedError(f"gdacs: {exc}") from exc
        features = (payload.get("features") or []) if isinstance(payload, dict) else []
        events: list[EventEnvelope] = []
        for feat in features:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            dist = haversine_km(CENTER[0], CENTER[1], lat, lon)
            if dist > MAX_DISTANCE_KM:
                continue
            events.append(self._to_event(props, lat, lon, dist))
        return events

    def _to_event(
        self, props: dict, lat: float, lon: float, dist_km: float
    ) -> EventEnvelope:
        now = datetime.now(timezone.utc)
        event_type = str(props.get("eventType") or "FL")
        alert_level = str(props.get("alertLevel") or "orange").lower()
        country = props.get("country") or "PK"
        incident_type = (
            IncidentType.FLOOD if event_type == "FL" else IncidentType.TRAFFIC_SPIKE
        )
        severity = (
            SeverityHint.SEVERE if alert_level == "red" else SeverityHint.MODERATE
        )
        alert_id = props.get("alertId") or now.strftime("%s")
        return EventEnvelope(
            event_id=f"evt-feed-gdacs-{alert_id}",
            incident_id=f"inc-feed-gdacs-{alert_id}",
            source_id="feed-gdacs",
            incident_type=incident_type,
            simulated_time=now,
            ingest_time=now,
            location=Location(
                zone=Zone.CENTRAL,
                lat=lat,
                lon=lon,
                road_segment_id="feed-gdacs",
            ),
            reported_attributes=ReportedAttributes(
                severity=severity,
                notes=(
                    f"GDACS {event_type} {alert_level} alert ({country}), "
                    f"{dist_km:.0f}km from Peshawar"
                ),
            ),
            quality_hints=QualityHints(is_synthetic=True),
        )
