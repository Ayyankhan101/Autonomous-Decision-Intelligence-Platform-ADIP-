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

    # valid override (life-safety priority raise = BREAK_GLASS tier, enhancement 4)
    ok = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": decision_id,
              "override_type": "CHANGE_PRIORITY", "reason": "confirmed by field",
              "new_priority": "CRITICAL", "break_glass": True},
    )
    assert ok.status_code == 200
    assert ok.json()["operator_id"] == "op-1"
    assert ok.json()["impact_tier"] == "BREAK_GLASS"
    assert ok.json()["break_glass"] is True

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


def test_bad_data_unknown_target_returns_404(client):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    before = client.get("/api/state").json()
    r = client.post(
        "/api/simulation/bad-data",
        json={"mode": "out_of_range", "target_incident_id": "inc-424242"},
    )
    assert r.status_code == 404
    after = client.get("/api/state").json()
    assert after["incident_count"] == before["incident_count"]
    assert after["decision_count"] == before["decision_count"]


def test_bad_recording_start_does_not_wipe_state(client):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    before = client.get("/api/state").json()
    assert before["incident_count"] == 1 and before["decision_count"] == 1
    r = client.post(
        "/api/simulation/start",
        json={"session_seed": 42, "scenario_seed": 7, "recording": "ghost.jsonl"},
    )
    assert r.status_code == 422
    after = client.get("/api/state").json()
    assert after["incident_count"] == 1
    assert after["decision_count"] == 1
    assert client.get("/api/decisions").json()["decisions"]


def test_audit_limit_is_bounded(client):
    assert client.get("/api/audit?limit=0").status_code == 422
    assert client.get("/api/audit?limit=-1").status_code == 422
    assert client.get("/api/audit?limit=1001").status_code == 422
    assert client.get("/api/audit?limit=1000").status_code == 200
    assert client.get("/api/audit?limit=1").status_code == 200


def test_change_priority_requires_new_priority(client):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    decision_id = client.get("/api/decisions").json()["decisions"][-1]["decision_id"]
    r = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": decision_id,
              "override_type": "CHANGE_PRIORITY", "reason": "no target priority"},
    )
    assert r.status_code == 422
    # unknown decision still 404 (checked before the missing-priority rule)
    r = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": "nope",
              "override_type": "CHANGE_PRIORITY", "reason": "x"},
    )
    assert r.status_code == 404
    # valid payload still works (life-safety raise requires break_glass, enhancement 4)
    r = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": decision_id,
              "override_type": "CHANGE_PRIORITY", "reason": "legit",
              "new_priority": "CRITICAL", "break_glass": True},
    )
    assert r.status_code == 200


def test_resume_does_not_wipe_session(client):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    before = client.get("/api/state").json()
    assert before["running"] is True
    assert client.post("/api/simulation/pause").status_code == 200
    assert client.get("/api/state").json()["running"] is False
    r = client.post("/api/simulation/resume")
    assert r.status_code == 200
    after = client.get("/api/state").json()
    assert after["running"] is True
    assert after["incident_count"] == before["incident_count"] == 1
    assert after["decision_count"] == before["decision_count"] == 1
    assert after["session_seed"] == before["session_seed"]


def test_multi_report_contradiction_routes_to_human_review(client):
    """Plan invariant 10: contradictory reports exist -> human review."""
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    r = client.post(
        "/api/simulation/incident",
        json={"incident_type": "fire", "zone": "south", "severity": "severe",
              "multi_report": True},
    )
    assert r.status_code == 200
    dec = client.get(f"/api/decisions/{r.json()['decision_ids'][0]}").json()
    assert dec["state"] == "HOLD_FOR_HUMAN"
    assert "R-DATA-QUALITY-HOLD-01" in dec["matched_rules"]
    assert "R-LOW-CONFIDENCE-HOLD-01" in dec["matched_rules"]
    assert any("conflicting" in reason or "contradict" in reason for reason in dec["reasons"])
    assert dec["overall_confidence"] < 0.6


def test_chained_overrides_dedupe_rule_ids(client):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    r = client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    dec_id = r.json()["decision_ids"][0]
    for i, override_type in enumerate(
        ("CHANGE_PRIORITY", "ASSIGN_RESOURCES", "MARK_DATA_UNTRUSTED", "ESCALATE_TO_HUMAN")
    ):
        body = {
            "decision_id": dec_id,
            "override_type": override_type,
            "operator_id": f"op-{i}",
            "reason": f"chained override {i}",
        }
        if override_type == "CHANGE_PRIORITY":
            body["new_priority"] = "CRITICAL"
            body["break_glass"] = True  # life-safety raise = BREAK_GLASS tier
        resp = client.post("/api/overrides", json=body)
        assert resp.status_code == 200
        latest = [
            d for d in client.get("/api/decisions").json()["decisions"]
            if d["incident_id"] == r.json()["incident_id"]
        ][-1]
        dec_id = latest["decision_id"]
        assert latest["matched_rules"].count("R-OVERRIDE-01") == 1
