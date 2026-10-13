"""Workstream B1 tests: feed infra, zone config, Peshawar fleet, /api/feeds routes."""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app
from jevcity.config import load_peshawar_geo
from jevcity.feeds import FeedError, FeedManager, GdacsFeed, ReliefWebFeed, SeismicFeed, WeatherFeed
from jevcity.feeds.base import FeedHealth
from jevcity.schemas import (
    EventEnvelope,
    FeedMode,
    IncidentType,
    Location,
    QualityHints,
    ReportedAttributes,
    SeverityHint,
    Zone,
)
from jevcity.simulation.resource_pool import PESHAWAR_FLEET, ResourcePool
from jevcity.simulation.state import SimulationState

# --- fixtures -------------------------------------------------------------

USGS_QUIKE_JSON = {
    "features": [
        {
            "properties": {"id": "us1000abcd", "mag": 4.8, "place": "12km NE of Peshawar", "time": 1758960000000},
            "geometry": {"coordinates": [71.65, 34.05, 10.0]},
        },
        {
            # out of bbox
            "properties": {"id": "far000", "mag": 5.0, "place": "Somewhere", "time": 1758960000000},
            "geometry": {"coordinates": [100.0, 40.0, 10.0]},
        },
        {
            # below magnitude
            "properties": {"id": "small0", "mag": 2.9, "place": "Nearby", "time": 1758960000000},
            "geometry": {"coordinates": [71.58, 34.01, 5.0]},
        },
    ]
}

GDACS_JSON = {
    "features": [
        {
            "properties": {"alertId": "FL123", "eventType": "FL", "alertLevel": "red", "country": "PK"},
            "geometry": {"coordinates": [71.50, 33.90]},
        },
        {
            "properties": {"alertId": "EQ999", "eventType": "EQ", "alertLevel": "orange", "country": "AF"},
            "geometry": {"coordinates": [71.0, 34.5]},  # ~60km — inside 300km
        },
        {
            "properties": {"alertId": "FAR1", "eventType": "FL", "alertLevel": "red", "country": "ID"},
            "geometry": {"coordinates": [120.0, -5.0]},  # far away
        },
    ]
}

RELIEFWEB_JSON = {
    "data": [
        {
            "fields": {
                "name": "Pakistan: Floods - Aug 2026",
                "url": {"url": "https://reliefweb.int/disaster/fl2026pakistan"},
                "date": {"created": "2026-08-14T12:00:00+00:00"},
            }
        }
    ]
}

OPEN_METEO_FLOOD_JSON = {
    "current": {
        "temperature_2m": 24.1,
        "precipitation": 12.5,
        "wind_speed_10m": 31.0,
        "weather_code": 65,
    }
}

OPEN_METEO_CALM_JSON = {
    "current": {
        "temperature_2m": 30.0,
        "precipitation": 0.0,
        "wind_speed_10m": 5.0,
        "weather_code": 1,
    }
}


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- zone config + fleet ---------------------------------------------------

def test_peshawar_geo_loads_five_zones_and_17_stations():
    geo = load_peshawar_geo()
    assert set(geo.zone_centroids) == set(Zone)
    assert set(geo.zone_polygons) == set(Zone)
    assert len(geo.stations) == 17
    for s in geo.stations:
        assert 33.9 <= s.lat <= 34.1
        assert 71.4 <= s.lon <= 71.7


def test_peshawar_fleet_pool_builds_fresh_each_reset():
    pool1 = ResourcePool(PESHAWAR_FLEET)
    assert pool1.available_count() == 17
    pool1.assign("amb-hbt-01", "inc-x")
    assert pool1.available_count() == 16

    sim = SimulationState(fleet=PESHAWAR_FLEET)
    assert sim.pool.available_count() == 17
    sim.pool.assign("amb-hbt-01", "inc-y")
    sim.reset()
    # reset builds a fresh pool from the spec — mutation does not leak
    assert sim.pool.available_count() == 17
    assert sim.pool.get("amb-hbt-01").status.value == "available"


def test_sim_pool_ids_differ_between_default_and_peshawar():
    default_ids = {r.resource_id for r in ResourcePool.default().all()}
    pesh_ids = {r.resource_id for r in ResourcePool(PESHAWAR_FLEET).all()}
    assert default_ids != pesh_ids
    assert "amb-hbt-01" in pesh_ids
    assert "amb-01" in default_ids


# --- feed health / circuit breaker -----------------------------------------

def test_circuit_breaker_opens_after_three_failures():
    health = FeedHealth(name="t")
    for _ in range(3):
        health.record_failure("boom")
    assert health.held_open()
    assert health.consecutive_failures == 3
    snap = health.snapshot()
    assert not snap.ok
    assert snap.detail == "boom"


def test_circuit_breaker_closes_on_success():
    health = FeedHealth(name="t")
    for _ in range(3):
        health.record_failure("boom")
    health.record_success(2, datetime.now(UTC))
    assert not health.held_open()
    assert health.consecutive_failures == 0
    assert health.snapshot().total_events == 2


# --- weather feed ----------------------------------------------------------

def test_weather_flood_risk_emits_flood_event():
    feed = WeatherFeed(_client_for(lambda req: httpx.Response(200, json=OPEN_METEO_FLOOD_JSON)))
    events = feed.poll()
    assert len(events) == 1
    ev = events[0]
    assert ev.incident_type == IncidentType.FLOOD
    assert "12.5mm/h" in (ev.reported_attributes.notes or "")
    assert feed.last_snapshot["flood_risk"] is True


def test_weather_calm_no_events():
    feed = WeatherFeed(_client_for(lambda req: httpx.Response(200, json=OPEN_METEO_CALM_JSON)))
    assert feed.poll() == []
    assert feed.last_snapshot["flood_risk"] is False


def test_weather_upstream_error_raises_feed_error():
    feed = WeatherFeed(_client_for(lambda req: httpx.Response(500)))
    with pytest.raises(FeedError):
        feed.poll()


# --- seismic feed ----------------------------------------------------------

def test_seismic_filters_bbox_and_magnitude():
    feed = SeismicFeed(_client_for(lambda req: httpx.Response(200, json=USGS_QUIKE_JSON)))
    events = feed.poll()
    assert len(events) == 1
    ev = events[0]
    assert "M4.8" in (ev.reported_attributes.notes or "")
    assert ev.incident_type == IncidentType.TRAFFIC_SPIKE
    assert ev.location.lat == pytest.approx(34.05)
    assert ev.quality_hints.is_synthetic is True


# --- gdacs feed ------------------------------------------------------------

def test_gdacs_distance_filter_and_type_mapping():
    feed = GdacsFeed(_client_for(lambda req: httpx.Response(200, json=GDACS_JSON)))
    events = feed.poll()
    assert len(events) == 2
    by_id = {e.event_id: e for e in events}
    fl = by_id["evt-feed-gdacs-FL123"]
    eq = by_id["evt-feed-gdacs-EQ999"]
    assert fl.incident_type == IncidentType.FLOOD
    assert fl.reported_attributes.severity == SeverityHint.SEVERE
    assert eq.incident_type == IncidentType.TRAFFIC_SPIKE
    assert eq.reported_attributes.severity == SeverityHint.MODERATE


# --- reliefweb feed --------------------------------------------------------

def test_reliefweb_returns_advisories_not_events():
    feed = ReliefWebFeed(_client_for(lambda req: httpx.Response(200, json=RELIEFWEB_JSON)))
    out = feed.poll()
    assert len(out) == 1
    assert out[0].title == "Pakistan: Floods - Aug 2026"
    assert out[0].url == "https://reliefweb.int/disaster/fl2026pakistan"
    assert feed.advisories == out


# --- FeedManager -----------------------------------------------------------

class _StubPoller:
    name = "stub"

    def __init__(self, events=None, error=None):
        self._events = events or []
        self._error = error
        self.calls = 0

    def poll(self):
        self.calls += 1
        if self._error:
            raise FeedError(self._error)
        return self._events


def _make_event(i: int) -> EventEnvelope:
    now = datetime.now(UTC)
    return EventEnvelope(
        event_id=f"evt-stub-{i}",
        incident_id=f"inc-stub-{i}",
        source_id="feed-stub",
        incident_type=IncidentType.ACCIDENT,
        simulated_time=now,
        ingest_time=now,
        location=Location(zone=Zone.NORTH, lat=34.01, lon=71.57, road_segment_id="stub"),
        reported_attributes=ReportedAttributes(severity=SeverityHint.MINOR),
        quality_hints=QualityHints(is_synthetic=True),
    )


def test_feed_manager_poll_once_appends_events():
    sim = SimulationState()
    stub = _StubPoller(events=[_make_event(1), _make_event(2)])
    mgr = FeedManager([stub], target=sim)
    ingested, errors = mgr.poll_once()
    assert ingested == 2
    assert errors == 0
    assert len(sim.events) == 2
    assert mgr.health("stub").total_events == 2


def test_feed_manager_swallows_poller_error():
    sim = SimulationState()
    bad = _StubPoller(error="down")
    mgr = FeedManager([bad], target=sim)
    ingested, errors = mgr.poll_once()
    assert ingested == 0
    assert errors == 1
    assert not mgr.health("stub").ok


def test_feed_manager_holds_broken_feed_open():
    sim = SimulationState()
    bad = _StubPoller(error="down")
    mgr = FeedManager([bad], target=sim)
    for _ in range(3):
        mgr.poll_once()
    assert mgr.health("stub").held_open()
    calls_before = bad.calls
    mgr.poll_once()
    assert bad.calls == calls_before  # circuit open: poller not called


# --- API routes ------------------------------------------------------------

def test_feeds_routes_mock_mode():
    client = TestClient(create_app(build_engine()))
    r = client.get("/api/feeds")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "mock"
    assert body["running"] is False
    assert body["feeds"] == []

    r2 = client.post("/api/feeds/refresh")
    assert r2.status_code == 409


def test_feeds_refresh_live_mode_with_mock_transport(monkeypatch):
    import jevcity.feeds.base as base_mod

    monkeypatch.setenv("JEVCITY_FEED_MODE", "live")
    handler = lambda req: httpx.Response(200, json=OPEN_METEO_CALM_JSON)  # noqa: E731
    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(base_mod.httpx, "Client", lambda **kw: mock_client)

    engine = build_engine(feed_mode=FeedMode.LIVE)
    client = TestClient(create_app(engine))
    r = client.get("/api/feeds")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "live"
    assert body["running"] is True
    assert {f["name"] for f in body["feeds"]} == {
        "weather", "seismic", "gdacs", "reliefweb",
    }

    r2 = client.post("/api/feeds/refresh")
    assert r2.status_code == 200
    assert "events_ingested" in r2.json()


def test_live_mode_uses_peshawar_fleet_and_wall_clock():
    import os

    os.environ["JEVCITY_FEED_MODE"] = "live"
    try:
        engine = build_engine(feed_mode=FeedMode.LIVE)
    finally:
        os.environ["JEVCITY_FEED_MODE"] = "mock"
    ids = {r.resource_id for r in engine.simulation.pool.all()}
    assert "amb-hbt-01" in ids
    # live clock starts near wall-clock (not the sim epoch)
    assert engine.simulation.clock.now.year == 2026
    assert engine.simulation.clock.now.month == 10


# --- B2: zone placement ----------------------------------------------------

def test_peshawar_pool_stations_have_coords():
    pool = ResourcePool.peshawar()
    res = pool.get("amb-hbt-01")
    assert res is not None
    assert res.lat is not None and res.lon is not None
    # Hayatabad ambulance station coords (real, workstream B1)
    assert abs(res.lat - 33.9895) < 1e-6
    assert abs(res.lon - 71.5700) < 1e-6


def test_default_pool_resources_have_no_coords():
    pool = ResourcePool.default()
    res = pool.get("amb-01")
    assert res is not None
    assert res.lat is None and res.lon is None


def test_inject_incident_with_lat_lon():
    sim = SimulationState()
    inc_id = sim.inject_incident(
        IncidentType.FLOOD, Zone.SOUTH, lat=34.008, lon=71.578
    )
    rec = sim.incidents[inc_id]
    assert rec.lat == 34.008
    assert rec.lon == 71.578


def test_inject_incident_without_lat_lon():
    sim = SimulationState()
    inc_id = sim.inject_incident(IncidentType.FIRE, Zone.CENTRAL)
    rec = sim.incidents[inc_id]
    # mock mode: zone centroid + jitter (not None — Location requires lat/lon)
    assert rec.lat is not None
    assert rec.lon is not None
    assert 33.995 < rec.lat < 34.020  # near central centroid 34.007 (±0.008)
    assert 71.565 < rec.lon < 71.585  # near central centroid 71.575 (±0.008)


def test_live_incident_route_accepts_lat_lon(monkeypatch):
    import jevcity.feeds.base as base_mod

    monkeypatch.setenv("JEVCITY_FEED_MODE", "live")
    handler = lambda req: httpx.Response(200, json=OPEN_METEO_CALM_JSON)  # noqa: E731
    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(base_mod.httpx, "Client", lambda **kw: mock_client)

    engine = build_engine(feed_mode=FeedMode.LIVE)
    engine.simulation.start(42, 7)  # resume: inject requires running
    client = TestClient(create_app(engine))
    r = client.post(
        "/api/simulation/incident",
        json={"incident_type": "flood", "zone": "south", "lat": 34.008, "lon": 71.578},
    )
    assert r.status_code == 200
    inc_id = r.json()["incident_id"]
    rec = engine.simulation.incidents[inc_id]
    assert rec.lat == 34.008
    assert rec.lon == 71.578
