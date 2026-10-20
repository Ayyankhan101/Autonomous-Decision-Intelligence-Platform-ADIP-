"""USGS seismic feed (free, no API key). Peshawar bbox + M>=4.0 filter.

IncidentType enum is frozen — honest mapping: a seismic event is surfaced as a
`traffic_spike` incident (the type that best matches "roads disrupted") with the
magnitude and distance in notes. No invented earthquake type.
"""
from __future__ import annotations

from datetime import datetime, timezone

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

from .base import FeedError, haversine_km

URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson"

BBOX = {"lat_min": 33.0, "lat_max": 35.5, "lon_min": 70.5, "lon_max": 72.5}
MIN_MAGNITUDE = 4.0
CENTER = (34.008, 71.578)


def _zone_for(lat: float, lon: float) -> Zone:
    """Nearest of the five zone centroids — a quake has no single zone; this
    just gives the map a stable anchor."""
    pts = {
        Zone.NORTH: (34.036, 71.565),
        Zone.SOUTH: (33.979, 71.565),
        Zone.EAST: (34.01, 71.64),
        Zone.WEST: (34.015, 71.495),
        Zone.CENTRAL: (34.007, 71.575),
    }
    return min(pts, key=lambda z: haversine_km(lat, lon, *pts[z]))


class SeismicFeed:
    name = "seismic"

    def __init__(self, client) -> None:
        self._client = client

    def poll(self) -> list[EventEnvelope]:
        try:
            resp = self._client.get(URL)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise FeedError(f"usgs: {exc}") from exc
        features = payload.get("features") or []
        events: list[EventEnvelope] = []
        for feat in features:
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            mag = props.get("mag")
            coords = geom.get("coordinates") or []
            if mag is None or len(coords) < 2:
                continue
            lat, lon = float(coords[1]), float(coords[0])
            if not (BBOX["lat_min"] <= lat <= BBOX["lat_max"]
                    and BBOX["lon_min"] <= lon <= BBOX["lon_max"]):
                continue
            if float(mag) < MIN_MAGNITUDE:
                continue
            events.append(self._to_event(props, lat, lon, float(mag)))
        return events

    def _to_event(
        self, props: dict, lat: float, lon: float, mag: float
    ) -> EventEnvelope:
        now = datetime.now(timezone.utc)
        dist_km = haversine_km(CENTER[0], CENTER[1], lat, lon)
        place = props.get("place") or "unknown"
        when_ms = props.get("time")
        when = (
            datetime.fromtimestamp(when_ms / 1000, tz=timezone.utc)
            if isinstance(when_ms, (int, float))
            else now
        )
        zone = _zone_for(lat, lon)
        return EventEnvelope(
            event_id=f"evt-feed-usgs-{props.get('id', now.strftime('%s'))}",
            incident_id=f"inc-feed-usgs-{props.get('id', now.strftime('%s'))}",
            source_id="feed-usgs",
            incident_type=IncidentType.TRAFFIC_SPIKE,
            simulated_time=when,
            ingest_time=now,
            location=Location(
                zone=zone,
                lat=lat,
                lon=lon,
                road_segment_id="feed-seismic",
            ),
            reported_attributes=ReportedAttributes(
                severity=SeverityHint.SEVERE if mag >= 5.5 else SeverityHint.MODERATE,
                notes=(
                    f"seismic event M{mag:.1f} {place}, "
                    f"{dist_km:.0f}km from Peshawar center"
                ),
            ),
            context=EventContext(),
            quality_hints=QualityHints(is_synthetic=True),
        )
