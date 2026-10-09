"""Enhancement 2: policy sandbox — three positions, objective weights, runtime switch."""
from __future__ import annotations

import copy

from jevcity.schemas import PolicyPosition

_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _start(client):
    r = client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    assert r.status_code == 200


def _inject(client, incident_type="accident", zone="north", severity="severe"):
    r = client.post(
        "/api/simulation/incident",
        json={"incident_type": incident_type, "zone": zone, "severity": severity},
    )
    assert r.status_code == 200
    return r.json()


def _decision(client, decision_id):
    r = client.get(f"/api/decisions/{decision_id}")
    assert r.status_code == 200
    return r.json()


def _decide(engine, incident_id, position, pool=None):
    return engine.decide_for(
        incident_id,
        pool=pool if pool is not None else copy.deepcopy(engine.simulation.pool),
        adapter=engine.adapter,
        dry_run=True,
        policy_position=position,
    )


def test_default_position_and_weights_recorded(client):
    _start(client)
    body = _inject(client, incident_type="accident", zone="north", severity="severe")
    did = body["decision_ids"][0]
    rec = _decision(client, did)
    assert rec["policy_position"] == "RESPONSE_TIME"
    assert rec["objective_weights"] == {
        "response_time": 1.0,
        "equity": 0.0,
        "emissions": 0.0,
    }
    assert rec["policy_version"]  # audit-trace completeness: version + position + weights
    state = client.get("/api/state").json()
    assert state["policy_position"] == "RESPONSE_TIME"
    assert state["objective_weights"]["response_time"] == 1.0


def test_eco_allocation_differs_from_response_time(client, engine):
    from jevcity.simulation.resource_pool import ResourcePool

    _start(client)
    body = _inject(client, incident_type="fire", zone="south", severity="severe")
    inc_id = _decision(client, body["decision_ids"][0])["incident_id"]

    # fresh pool: compare allocation rules on equal footing (inject already
    # consumed fire-02 on the live pool)
    resp = _decide(engine, inc_id, PolicyPosition.RESPONSE_TIME, pool=ResourcePool())
    eco = _decide(engine, inc_id, PolicyPosition.ECO, pool=ResourcePool())
    # South fire: baseline picks same-zone fire-02 (eco 0.3); ECO picks fire-01 (eco 0.9).
    assert resp.assigned_resource_ids == ["fire-02"]
    assert eco.assigned_resource_ids == ["fire-01"]
    assert "R-ECO-ELECTRIC-FIRST-01" in eco.matched_rules
    assert "R-ECO-ELECTRIC-FIRST-01" not in resp.matched_rules
    assert eco.objective_weights["emissions"] == 1.0


def test_equity_boosts_underserved_zone_only(client, engine):
    _start(client)
    north = _inject(client, incident_type="flood", zone="north", severity="moderate")
    central = _inject(client, incident_type="flood", zone="central", severity="moderate")
    north_id = _decision(client, north["decision_ids"][0])["incident_id"]
    central_id = _decision(client, central["decision_ids"][0])["incident_id"]

    resp = _decide(engine, north_id, PolicyPosition.RESPONSE_TIME)
    eq = _decide(engine, north_id, PolicyPosition.EQUITY)
    assert _RANK[eq.priority.value] >= _RANK[resp.priority.value]
    if eq.priority != resp.priority:
        assert "R-EQUITY-UNSERVED-01" in eq.matched_rules
        assert eq.objective_weights["equity"] == 1.0
    else:
        # already at the cap — equity must not push past CRITICAL
        assert eq.priority.value == "CRITICAL"

    resp_c = _decide(engine, central_id, PolicyPosition.RESPONSE_TIME)
    eq_c = _decide(engine, central_id, PolicyPosition.EQUITY)
    assert eq_c.priority == resp_c.priority
    assert "R-EQUITY-UNSERVED-01" not in eq_c.matched_rules


def test_switch_report_and_audit(client, engine):
    _start(client)
    body = _inject(client, incident_type="fire", zone="south", severity="severe")
    did = body["decision_ids"][0]
    rec = _decision(client, did)
    assert rec["assigned_resource_ids"] == ["fire-02"]

    r = client.post(
        "/api/policy/position", json={"position": "ECO", "reoptimise_active": False}
    )
    assert r.status_code == 200
    out = r.json()
    assert out["previous_position"] == "RESPONSE_TIME"
    assert out["position"] == "ECO"
    assert out["objective_weights"] == {
        "response_time": 0.0,
        "equity": 0.0,
        "emissions": 1.0,
    }
    assert did in out["affected_decisions"]
    assert out["reoptimised"] == 0
    assert engine.policy_position == PolicyPosition.ECO

    # switch applies to NEW decisions only — the live record is untouched
    assert _decision(client, did)["assigned_resource_ids"] == ["fire-02"]

    audit = client.get("/api/audit").json()["entries"]
    switch_entries = [a for a in audit if a["action"] == "POLICY_POSITION_SWITCHED"]
    assert len(switch_entries) == 1
    assert "RESPONSE_TIME -> ECO" in switch_entries[0]["reason"]

    state = client.get("/api/state").json()
    assert state["policy_position"] == "ECO"


def test_reoptimise_creates_new_records_append_only(client, engine):
    _start(client)
    body = _inject(client, incident_type="fire", zone="south", severity="severe")
    did = body["decision_ids"][0]
    history_before = len(engine.decision_history)

    r = client.post(
        "/api/policy/position", json={"position": "ECO", "reoptimise_active": True}
    )
    assert r.status_code == 200
    out = r.json()
    assert did in out["affected_decisions"]
    assert out["reoptimised"] >= 1

    # append-only: old record survives with its original allocation
    old = _decision(client, did)
    assert old["assigned_resource_ids"] == ["fire-02"]
    assert old["policy_position"] == "RESPONSE_TIME"
    assert len(engine.decision_history) > history_before

    # the incident now has a newer ECO decision on record
    inc_rec = client.get(f"/api/incidents/{old['incident_id']}").json()
    latest = inc_rec["latest_decision"]
    assert latest["decision_id"] != did
    assert latest["policy_position"] == "ECO"
    assert latest["assigned_resource_ids"] == ["fire-01"]

    # units released + reassigned to the same incident
    pool = engine.simulation.pool
    assert pool.get("fire-02").status.value == "available"
    assert pool.get("fire-01").assigned_incident_id == old["incident_id"]


def test_switch_same_position_is_noop(client, engine):
    _start(client)
    history_before = len(engine.decision_history)
    r = client.post(
        "/api/policy/position",
        json={"position": "RESPONSE_TIME", "reoptimise_active": True},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["affected_decisions"] == []
    assert out["reoptimised"] == 0
    assert len(engine.decision_history) == history_before


def test_invalid_position_rejected(client):
    _start(client)
    r = client.post("/api/policy/position", json={"position": "BOGUS"})
    assert r.status_code == 422
    r = client.post(
        "/api/policy/position",
        json={"position": "ECO", "reoptimise_active": True, "extra": 1},
    )
    assert r.status_code == 422  # extra=forbid


def test_switch_then_new_decision_uses_new_position(client, engine):
    _start(client)
    _inject(client, incident_type="accident", zone="north", severity="severe")
    r = client.post("/api/policy/position", json={"position": "EQUITY"})
    assert r.status_code == 200
    body = _inject(client, incident_type="flood", zone="west", severity="moderate")
    did = body["decision_ids"][0]
    rec = _decision(client, did)
    assert rec["policy_position"] == "EQUITY"
    assert rec["objective_weights"] == {
        "response_time": 0.0,
        "equity": 1.0,
        "emissions": 0.0,
    }
