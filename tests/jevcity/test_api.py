from __future__ import annotations

from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app
from jevcity.schemas import LayaMode



def test_state_payload_shape(client):
    resp = client.get("/api/state")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "simulated_time", "running", "session_seed", "scenario_seed",
        "incident_count", "decision_count", "available_resources",
        "laya_mode", "last_laya_status",
    ):
        assert key in body
    assert body["laya_mode"] == "mock"


def test_full_simulation_flow(client):
    # start seeded session
    r = client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    assert r.status_code == 200

    # inject incident → decision produced
    r = client.post(
        "/api/simulation/incident",
        json={
            "incident_type": "accident",
            "zone": "north",
            "severity": "severe",
            "multi_report": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["incident_id"]
    assert len(body["decision_ids"]) == 1

    # reads
    assert client.get("/api/incidents").json()["incidents"]
    inc_id = body["incident_id"]
    detail = client.get(f"/api/incidents/{inc_id}").json()
    assert detail["incident"]["incident_id"] == inc_id
    assert detail["latest_decision"] is not None

    decisions = client.get("/api/decisions").json()["decisions"]
    assert decisions
    decision_id = decisions[-1]["decision_id"]
    single = client.get(f"/api/decisions/{decision_id}").json()
    assert single["policy_version"]
    assert single["laya"]["status"]

    assert client.get("/api/resources").json()["resources"]
    audit = client.get("/api/audit").json()["entries"]
    assert audit and audit[0]["action"] == "DECISION_EMITTED"

    # override requires actor + reason (422 without)
    bad = client.post(
        "/api/overrides",
        json={"operator_id": "", "decision_id": decision_id,
              "override_type": "CHANGE_PRIORITY", "reason": "x"},
    )
    assert bad.status_code == 422
    bad2 = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": decision_id,
              "override_type": "CHANGE_PRIORITY", "reason": ""},
    )
    assert bad2.status_code == 422

    # valid override
    ok = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": decision_id,
              "override_type": "CHANGE_PRIORITY", "reason": "confirmed by field",
              "new_priority": "CRITICAL"},
    )
    assert ok.status_code == 200
    assert ok.json()["operator_id"] == "op-1"

    # original decision still visible (append-only history)
    history = client.get("/api/decisions").json()["decisions"]
    assert any(d["decision_id"] == decision_id for d in history)
    override_entries = [e for e in client.get("/api/audit").json()["entries"]
                        if e["action"] == "OVERRIDE_APPLIED"]
    assert override_entries and override_entries[0]["reason"] == "confirmed by field"

    # what-if
    wf = client.post("/api/what-if/run", json={"scenario": "remove_one_ambulance"})
    assert wf.status_code == 200
    wf_body = wf.json()
    assert wf_body["dry_run"] is True
    assert wf_body["audit_written"] is False
    assert wf_body["live_state_mutated"] is False
    sid = wf_body["sandbox_id"]
    got = client.get(f"/api/what-if/{sid}/result").json()
    assert got["sandbox_id"] == sid


def test_bad_data_and_second_emergency_endpoints(client):
    client.post("/api/simulation/start", json={"session_seed": 1, "scenario_seed": 2})
    bad = client.post(
        "/api/simulation/bad-data", json={"mode": "out_of_range"}
    )
    assert bad.status_code == 200
    decision_ids = bad.json()["decision_ids"]
    record = client.get(f"/api/decisions/{decision_ids[-1]}").json()
    assert record["state"] == "REJECTED_INPUT"

    second = client.post(
        "/api/simulation/second-emergency",
        json={"incident_type": "fire", "zone": "south"},
    )
    assert second.status_code == 200
    assert second.json()["incident_id"]


def test_pause_reset_controls(client):
    client.post("/api/simulation/start", json={"session_seed": 5, "scenario_seed": 6})
    assert client.post("/api/simulation/pause").status_code == 200
    assert client.get("/api/state").json()["running"] is False
    client.post("/api/simulation/incident",
                json={"incident_type": "flood", "zone": "east", "severity": "minor"})
    assert client.post(
        "/api/simulation/reset", json={"session_seed": 5, "scenario_seed": 6}
    ).status_code == 200
    state = client.get("/api/state").json()
    assert state["incident_count"] == 0
    assert state["decision_count"] == 0


def test_404s(client):
    assert client.get("/api/incidents/nope").status_code == 404
    assert client.get("/api/decisions/nope").status_code == 404
    assert client.get("/api/what-if/nope/result").status_code == 404
    assert client.post(
        "/api/overrides",
        json={"operator_id": "op", "decision_id": "nope",
              "override_type": "CHANGE_PRIORITY", "reason": "x"},
    ).status_code == 404


def test_reset_clears_laya_cache():
    engine = build_engine(mode=LayaMode.CACHE)
    client = TestClient(create_app(engine))
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    assert engine.adapter.cache  # populated by the incident decision
    client.post(
        "/api/simulation/reset",
        json={"session_seed": 42, "scenario_seed": 7},
    )
    assert engine.adapter.cache == {}


def test_incident_after_restart_produces_decision():
    client = TestClient(create_app())
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "fire", "zone": "south", "severity": "minor"},
    )
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    r = client.post(
        "/api/simulation/incident",
        json={"incident_type": "flood", "zone": "east", "severity": "minor"},
    )
    assert r.json()["decision_ids"]


def test_restart_with_recording_leaves_no_stale_decisions():
    engine = build_engine()
    client = TestClient(create_app(engine))
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    r = client.post(
        "/api/simulation/start",
        json={"session_seed": 42, "scenario_seed": 7, "recording": "sim-session-v1.jsonl"},
    )
    ids = r.json()["decision_ids"]
    state = client.get("/api/state").json()
    assert state["decision_count"] == len(ids)
