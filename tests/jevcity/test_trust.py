"""Enhancement 1: per-stream trust scoring — Sybil flood detection, clean-stream
false-positive guard, gradual recovery, burst rate rule (spec Table 2 metrics)."""
from __future__ import annotations

from datetime import datetime, timedelta

from jevcity.ingestion.trust import (
    FLAG_THRESHOLD,
    RATE_LIMIT,
    TRUST_GATE,
    TrustRegistry,
)
from jevcity.schemas import EventEnvelope, SeverityHint


def _event(
    *,
    event_id: str,
    source_id: str,
    severity: SeverityHint,
    when: datetime,
    incident_id: str = "inc-00001",
) -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": event_id,
            "incident_id": incident_id,
            "source_id": source_id,
            "event_type": "incident_report",
            "incident_type": "accident",
            "simulated_time": when.isoformat(),
            "ingest_time": when.isoformat(),
            "location": {
                "zone": "east",
                "lat": 51.5,
                "lon": -0.14,
                "road_segment_id": "rs-01",
            },
            "reported_attributes": {
                "severity": severity.value,
                "vehicles_involved": 2,
                "injuries_reported": 1,
                "lanes_blocked": 1,
                "notes": None,
            },
            "context": {
                "weather": "clear",
                "traffic_level": "moderate",
                "time_of_day_bucket": None,
            },
            "quality_hints": {"is_synthetic": False, "injection_mode": None},
        }
    )


def _start(client):
    r = client.post(
        "/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7}
    )
    assert r.status_code == 200


def test_clean_streams_not_flagged(client, engine):
    """Metric: false-positive rate on clean streams — agreeing sources stay trusted."""
    _start(client)
    r = client.post(
        "/api/simulation/incident",
        json={
            "incident_type": "accident",
            "zone": "east",
            "severity": "severe",
            "multi_report": False,
        },
    )
    assert r.status_code == 200
    state = client.get("/api/state").json()
    assert state["decision_count"] == 1
    decisions = client.get("/api/decisions").json()["decisions"]
    record = decisions[-1]
    assert record["trust"] is not None
    assert record["trust"]["mean_veracity"] >= 0.9
    assert record["trust"]["flagged_sources"] == []
    assert "R-TRUST-DOWNWEIGHT-01" not in record["matched_rules"]


def test_sybil_flood_flags_fake_sources(client, engine):
    """Sybil flood: fake identities flagged, mean veracity below gate, rule fires."""
    _start(client)
    r = client.post("/api/simulation/sybil", json={"reports": 5})
    assert r.status_code == 200
    out = r.json()
    assert len(out["fake_sources"]) == 5
    assert out["fake_sources"][0].startswith("sybil-walker-")

    decisions = client.get("/api/decisions").json()["decisions"]
    record = decisions[-1]
    assert record["incident_id"] == out["incident_id"]
    assert record["trust"] is not None
    trust = record["trust"]
    assert trust["mean_veracity"] < TRUST_GATE
    assert trust["flagged_sources"] == out["fake_sources"]
    assert "R-TRUST-DOWNWEIGHT-01" in record["matched_rules"]
    assert all(trust["source_scores"][s] < FLAG_THRESHOLD for s in out["fake_sources"])
    assert trust["source_scores"]["sensor-auto-01"] == 1.0

    incident = client.get(f"/api/incidents/{out['incident_id']}").json()["incident"]
    for s in out["fake_sources"]:
        assert s in incident["source_ids"]


def test_sybil_downweights_vs_clean(client, engine):
    """Metric: decision quality degrades under attack relative to baseline."""
    _start(client)
    r = client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "east", "severity": "severe"},
    )
    assert r.status_code == 200
    baseline = client.get("/api/decisions").json()["decisions"][-1]

    r = client.post("/api/simulation/sybil", json={"reports": 5})
    assert r.status_code == 200
    under_attack = client.get("/api/decisions").json()["decisions"][-1]

    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    assert order[under_attack["priority"]] < order[baseline["priority"]]
    assert "R-TRUST-DOWNWEIGHT-01" in under_attack["matched_rules"]
    assert under_attack["state"] != baseline["state"] or (
        under_attack["priority"] != baseline["priority"]
    )
    assert under_attack["trust"]["mean_veracity"] < baseline["trust"]["mean_veracity"]


def test_trust_recovers_gradually(client, engine):
    """Metric: recovery after an anomaly ends — penalised source climbs back, is
    never permanently blacklisted."""
    reg = TrustRegistry()
    base = datetime(2026, 9, 27, 10, 0, 0)
    primary = _event(
        event_id="evt-000001",
        source_id="primary-sensor",
        severity=SeverityHint.SEVERE,
        when=base,
    )
    disagree = _event(
        event_id="evt-000002",
        source_id="noisy-sensor",
        severity=SeverityHint.MINOR,
        when=base + timedelta(seconds=1),
    )
    reg.observe([primary, disagree])
    penalised = reg.veracity["noisy-sensor"]
    assert penalised < 1.0
    assert penalised >= 0.0

    for i in range(6):
        clean = _event(
            event_id=f"evt-clean-{i}",
            source_id="noisy-sensor",
            severity=SeverityHint.SEVERE,
            when=base + timedelta(seconds=300 + 300 * i),
            incident_id=f"inc-{i + 2:05d}",
        )
        reg.observe([clean])
    recovered = reg.veracity["noisy-sensor"]
    assert recovered > penalised
    assert recovered >= FLAG_THRESHOLD


def test_sybil_route_validates_bounds(client, engine):
    _start(client)
    r = client.post("/api/simulation/sybil", json={"reports": 1})
    assert r.status_code == 422
    r = client.post("/api/simulation/sybil", json={"reports": 11})
    assert r.status_code == 422
    r = client.post("/api/simulation/sybil", json={"bogus": True})
    assert r.status_code == 422  # extra=forbid


def test_rate_burst_penalises_single_source(client, engine):
    """Report-rate anomaly: one identity flooding within the window loses veracity."""
    reg = TrustRegistry()
    base = datetime(2026, 9, 27, 10, 0, 0)
    for i in range(RATE_LIMIT + 2):
        reg.observe(
            [
                _event(
                    event_id=f"evt-burst-{i}",
                    source_id="burst-source",
                    severity=SeverityHint.MODERATE,
                    when=base + timedelta(seconds=i),
                    incident_id=f"inc-{i:05d}",
                )
            ]
        )
    assert reg.veracity["burst-source"] < FLAG_THRESHOLD
    assert "burst-source" in reg.flagged()


def test_trust_reset_on_session_reset(client, engine):
    _start(client)
    r = client.post("/api/simulation/sybil", json={"reports": 4})
    assert r.status_code == 200
    assert engine.trust.flagged()

    r = client.post("/api/simulation/reset", json={"session_seed": 42, "scenario_seed": 7})
    assert r.status_code == 200
    assert engine.trust.flagged() == []
    assert engine.trust.veracity == {}
