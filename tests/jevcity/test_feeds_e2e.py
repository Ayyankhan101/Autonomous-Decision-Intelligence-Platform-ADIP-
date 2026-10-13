"""Workstream B4: recorded-fixture E2E tests (network-free CI).

Pollers replay committed fixtures under datasets/jevcity/feeds/; FeedManager
start/stop/circuit-break verified end-to-end; /api/feeds shape asserted.
Re-record: JEVCITY_FEED_RECORD=1 uv run pytest tests/jevcity/test_feeds_e2e.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app
from jevcity.feeds import FeedManager, GdacsFeed, ReliefWebFeed, SeismicFeed, WeatherFeed
from jevcity.schemas import FeedMode
from jevcity.simulation.state import SimulationState

FIXTURES = Path(__file__).parent.parent.parent / "datasets" / "jevcity" / "feeds"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _client_for(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- fixture-based poller tests -------------------------------------------

def test_weather_poller_replays_fixture():
    data = _load_fixture("open-meteo")
    client = _client_for(lambda req: httpx.Response(200, json=data))
    feed = WeatherFeed(client)
    events = feed.poll()
    assert len(events) >= 1
    assert events[0].incident_type.value == "flood"


def test_seismic_poller_replays_fixture():
    data = _load_fixture("usgs-seismic")
    client = _client_for(lambda req: httpx.Response(200, json=data))
    feed = SeismicFeed(client)
    events = feed.poll()
    # bbox + mag filter: us1000abcd passes, far000 + small0 filtered
    assert len(events) == 1
    assert events[0].incident_id  # has real coords from fixture


def test_gdacs_poller_replays_fixture():
    data = _load_fixture("gdacs")
    client = _client_for(lambda req: httpx.Response(200, json=data))
    feed = GdacsFeed(client)
    events = feed.poll()
    # FL123 (PK, red, 300km) + EQ999 (AF, orange, ~60km); FAR1 filtered
    assert len(events) == 2


def test_reliefweb_poller_replays_fixture():
    data = _load_fixture("reliefweb")
    client = _client_for(lambda req: httpx.Response(200, json=data))
    feed = ReliefWebFeed(client)
    advisories = feed.poll()
    assert len(advisories) == 1
    assert "Pakistan" in advisories[0].title


# --- FeedManager E2E (start/stop/circuit-break) ---------------------------

def test_feed_manager_lifecycle_full_cycle():
    sim = SimulationState()
    calm = _load_fixture("open-meteo")["current"]
    handler = lambda req: httpx.Response(200, json={"current": calm})  # noqa: E731
    client = _client_for(handler)
    weather = WeatherFeed(client)
    mgr = FeedManager([weather], target=sim, client=client)

    assert not mgr._stop.is_set()
    mgr.start()
    assert mgr._thread is not None and mgr._thread.is_alive()
    # poll_once on started manager: one clean cycle
    ingested, errors = mgr.poll_once()
    assert errors == 0
    assert ingested >= 1  # weather fixture has precipitation 12.5 → flood event
    mgr.stop()
    assert mgr._thread is None


def test_feed_manager_circuit_break_open_close():
    sim = SimulationState()
    fail_count = 0

    def handler(req):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 3:
            raise httpx.ConnectError("simulated outage")
        return httpx.Response(200, json=_load_fixture("open-meteo"))

    client = _client_for(handler)
    weather = WeatherFeed(client)
    mgr = FeedManager([weather], target=sim, client=client)

    # 3 failures → circuit opens
    for _ in range(3):
        mgr.poll_once()
    health = mgr.health("weather")
    assert health.consecutive_failures == 3
    assert health.held_open()

    # after probe cooldown, circuit closes on success
    health._held_until = 0  # force probe
    ingested, errors = mgr.poll_once()
    assert errors == 0
    assert mgr.health("weather").consecutive_failures == 0


# --- /api/feeds shape ------------------------------------------------------

def test_feeds_endpoint_shape_live_mode(monkeypatch):
    monkeypatch.setenv("JEVCITY_FEED_MODE", "live")
    calm = _load_fixture("open-meteo")
    handler = lambda req: httpx.Response(200, json=calm)  # noqa: E731
    mock_client = _client_for(handler)
    import jevcity.feeds.base as base_mod
    monkeypatch.setattr(base_mod.httpx, "Client", lambda **kw: mock_client)

    engine = build_engine(feed_mode=FeedMode.LIVE)
    client = TestClient(create_app(engine))
    r = client.get("/api/feeds")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "live"
    assert body["running"] is True
    assert isinstance(body["feeds"], list)
    assert len(body["feeds"]) == 4  # weather, seismic, gdacs, reliefweb
    for f in body["feeds"]:
        assert set(f.keys()) >= {"name", "ok", "consecutive_failures", "events_last_poll", "total_events"}
    assert body["weather"] is None or isinstance(body["weather"], dict)
    assert isinstance(body["advisories"], list)
