"""Open-Meteo weather feed (free, no API key). Peshawar coordinates.

Weather itself is context (`EventContext.weather`); heavy precipitation raises a
flood-risk flag. When flood risk is on, a synthetic flood suggestion is appended
for the lowest-lying zone — honest because it is labeled as feed-derived and the
same deterministic validation/policy path applies.
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
    Zone,
)

from .base import FeedError

URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=34.008&longitude=71.578"
    "&current=temperature_2m,precipitation,wind_speed_10m,weather_code"
)

# WMO weather codes worth mapping (subset; unknown codes → "unknown").
_CODE_LABELS = {
    0: "clear", 1: "mainly_clear", 2: "partly_cloudy", 3: "overcast",
    45: "fog", 48: "rime_fog",
    51: "light_drizzle", 53: "drizzle", 55: "dense_drizzle",
    61: "light_rain", 63: "rain", 65: "heavy_rain",
    80: "rain_showers", 81: "heavy_rain_showers", 82: "violent_showers",
    95: "thunderstorm", 96: "thunderstorm_hail", 99: "thunderstorm_heavy_hail",
}
FLOOD_RAIN_MM_H = 7.5  # Open-Meteo precipitation is mm over the last hour


class WeatherFeed:
    name = "weather"

    def __init__(self, client, lowest_zone: Zone = Zone.SOUTH) -> None:
        self._client = client
        self._lowest_zone = lowest_zone
        self.last_snapshot: dict | None = None

    def poll(self) -> list[EventEnvelope]:
        try:
            resp = self._client.get(URL)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise FeedError(f"open-meteo: {exc}") from exc
        current = payload.get("current") or {}
        try:
            temp = float(current["temperature_2m"])
            precip = float(current["precipitation"])
            wind = float(current["wind_speed_10m"])
            code = int(current["weather_code"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FeedError(f"open-meteo bad payload: {exc}") from exc

        summary = _CODE_LABELS.get(code, "unknown")
        flood_risk = precip >= FLOOD_RAIN_MM_H
        self.last_snapshot = {
            "temperature_c": temp,
            "precipitation_mm": precip,
            "wind_speed_kmh": wind,
            "weather_code": code,
            "summary": summary,
            "flood_risk": flood_risk,
        }
        if not flood_risk:
            return []
        return [self._flood_suggestion(temp, precip, wind, summary)]

    def _flood_suggestion(
        self, temp: float, precip: float, wind: float, summary: str
    ) -> EventEnvelope:
        now = datetime.now(timezone.utc)
        zone = self._lowest_zone
        return EventEnvelope(
            event_id=f"evt-feed-weather-{now.strftime('%Y%m%dT%H%M%S')}",
            incident_id=f"inc-feed-weather-{now.strftime('%Y%m%dT%H%M%S')}",
            source_id="feed-open-meteo",
            incident_type=IncidentType.FLOOD,
            simulated_time=now,
            ingest_time=now,
            location=Location(
                zone=zone,
                lat=33.979,
                lon=71.565,
                road_segment_id="feed-lowest-zone",
            ),
            reported_attributes=ReportedAttributes(
                notes=(
                    f"feed-derived flood risk: {precip}mm/h precipitation "
                    f"(threshold {FLOOD_RAIN_MM_H}), {summary}, "
                    f"{temp}C, wind {wind}km/h"
                ),
            ),
            context=EventContext(weather=summary),
            quality_hints=QualityHints(is_synthetic=True),
        )
