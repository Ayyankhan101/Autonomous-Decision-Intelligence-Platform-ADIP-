"""DEMO_RUNBOOK §2 executable walkthrough: graded beats chained in one session,
ending with a full hash-chain verify — the API-level twin of the rehearsal script."""
from __future__ import annotations

import pytest


def test_graded_beats_end_to_end_with_chain_verify(client, engine):
    started = client.post(
        "/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7}
    )
    assert started.status_code == 200
    state = client.get("/api/state").json()
    assert state["session_seed"] == 42
    assert state["audit_write_failed"] is False

    # beat 2-3: incident + model outputs visible on the decision
    created = client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "multi_report": True},
    )
    assert created.status_code == 200
    decision_id = created.json()["decision_ids"][0]
    decision = client.get(f"/api/decisions/{decision_id}").json()
    assert decision["signals"]["severity"]["confidence"] is not None
    assert decision["signals"]["traffic"]["confidence"] is not None
    assert decision["laya"] is not None  # beat 10: suggestion block present

    # beat 4-5: bad-data injection still yields a guarded decision
    bad = client.post(
        "/api/simulation/bad-data", json={"mode": "conflicting_reports"}
    )
    assert bad.status_code == 200
    bad_decision = client.get(
        f"/api/decisions/{bad.json()['decision_ids'][0]}"
    ).json()
    assert bad_decision["matched_rules"]

    # beat 7: human override with mandatory reason
    overridden = client.post(
        "/api/overrides",
        json={
            "operator_id": "op-1",
            "decision_id": decision_id,
            "override_type": "CHANGE_PRIORITY",
            "new_priority": "MEDIUM",
            "reason": "field report contradicts severity",
        },
    )
    assert overridden.status_code == 200
    rejected = client.post(
        "/api/overrides",
        json={
            "operator_id": "op-1",
            "decision_id": decision_id,
            "override_type": "CHANGE_PRIORITY",
            "new_priority": "LOW",
            "reason": "",
        },
    )
    assert rejected.status_code == 422

    # beat 8: What-If sandbox writes nothing to the live audit log
    audit_before = len(engine.audit.entries(limit=1000))
    what_if = client.post(
        "/api/what-if/run", json={"scenario": "remove_one_ambulance"}
    )
    assert what_if.status_code == 200
    assert what_if.json()["dry_run"] is True
    assert len(engine.audit.entries(limit=1000)) == audit_before

    # beat 19 (optional): Sybil flood attaches a trust block
    sybil = client.post(
        "/api/simulation/sybil",
        json={"incident_type": "accident", "zone": "east", "reports": 5},
    )
    assert sybil.status_code == 200
    sybil_decision = client.get(
        f"/api/decisions/{sybil.json()['decision_ids'][0]}"
    ).json()
    assert sybil_decision["trust"] is not None
    assert sybil_decision["trust"]["flagged_sources"]

    # beat 18 (optional): policy sandbox switch applies new weights
    switched = client.post(
        "/api/policy/position", json={"position": "EQUITY"}
    )
    assert switched.status_code == 200
    body = switched.json()
    assert body["position"] == "EQUITY"
    assert sum(body["objective_weights"].values()) == pytest.approx(1.0)

    # final pre-flight: intact chain after every write above
    verify = client.get("/api/audit/verify").json()
    assert verify["ok"] is True
    assert verify["broken_at"] is None
    assert client.get("/api/state").json()["audit_write_failed"] is False


def test_runbook_laya_degraded_beat_keeps_operating(client, engine):
    from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
    from jevcity.schemas import LayaMode, LayaStatus

    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    engine.adapter = LayaAdapter(mode=LayaMode.MOCK, force_status=LayaStatus.TIMEOUT)

    created = client.post(
        "/api/simulation/incident",
        json={"incident_type": "fire", "zone": "south"},
    )
    assert created.status_code == 200
    record = client.get(
        f"/api/decisions/{created.json()['decision_ids'][0]}"
    ).json()
    assert record["laya"]["status"] == "timeout"
    assert record["state"] in ("HOLD_FOR_HUMAN", "MODEL_DEGRADED")
    assert record["matched_rules"]

    verify = client.get("/api/audit/verify").json()
    assert verify["ok"] is True
