from __future__ import annotations


def _start(client):
    r = client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    assert r.status_code == 200


def _inject(client, **overrides):
    payload = {"incident_type": "accident", "zone": "north", "severity": "severe"}
    payload.update(overrides)
    r = client.post("/api/simulation/incident", json=payload)
    assert r.status_code == 200
    return r.json()


def test_fresh_decision_has_lineage(client):
    _start(client)
    body = _inject(client)
    decision = client.get(f"/api/decisions/{body['decision_ids'][0]}").json()
    lineage = decision["lineage"]
    assert lineage is not None, "every new decision must carry a lineage block"
    assert len(lineage["terms"]) >= 3
    assert lineage["clause_id"] is not None
    assert lineage["clause_id"] in decision["matched_rules"]
    assert f"CLAUSE {lineage['clause_id']}" in lineage["expression"]
    for term in lineage["terms"]:
        assert 0.0 <= term["score"] <= 1.0
        assert term["direction"] in ("positive", "negative", "neutral")
        assert term["source"]


def test_rejected_decision_has_lineage(client):
    _start(client)
    body = client.post("/api/simulation/bad-data", json={"mode": "missing_fields"}).json()
    decision = client.get(f"/api/decisions/{body['decision_ids'][0]}").json()
    lineage = decision["lineage"]
    assert lineage is not None
    assert lineage["clause_id"] == "R-INPUT-REJECT-01"
    assert decision["state"] == "REJECTED_INPUT"


def test_contention_lineage_has_scarcity_term(client):
    _start(client)
    last_id = None
    for _ in range(4):
        body = client.post("/api/simulation/second-emergency", json={}).json()
        last_id = body["decision_ids"][0]
    decision = client.get(f"/api/decisions/{last_id}").json()
    assert decision["state"] == "CONTENTION_ESCALATION"
    terms = {t["label"]: t for t in decision["lineage"]["terms"]}
    assert terms["resource_scarcity"]["score"] == 1.0
    assert terms["resource_scarcity"]["direction"] == "negative"
    assert decision["lineage"]["clause_id"] == "R-CONTENTION-ESCALATE-01"


def test_override_carries_clause_attribution(client):
    _start(client)
    body = _inject(client)
    resp = client.post(
        "/api/overrides",
        json={
            "decision_id": body["decision_ids"][0],
            "override_type": "CHANGE_PRIORITY",
            "new_priority": "MEDIUM",
            "operator_id": "op-clause-test",
            "reason": "clause disputed by field report",
            "cited_clause": "R-AUTO-APPROVE-01",
            "reason_code": "POLICY_CLAUSE",
        },
    )
    assert resp.status_code == 200
    record = resp.json()
    assert record["cited_clause"] == "R-AUTO-APPROVE-01"
    assert record["reason_code"] == "POLICY_CLAUSE"

    latest = [
        d for d in client.get("/api/decisions").json()["decisions"]
        if d["incident_id"] == body["incident_id"]
    ][-1]
    assert latest["override"]["cited_clause"] == "R-AUTO-APPROVE-01"
    assert latest["override"]["reason_code"] == "POLICY_CLAUSE"


def test_override_attribution_optional_for_compatibility(client):
    _start(client)
    body = _inject(client)
    resp = client.post(
        "/api/overrides",
        json={
            "decision_id": body["decision_ids"][0],
            "override_type": "ESCALATE_TO_HUMAN",
            "operator_id": "op-compat",
            "reason": "no attribution fields supplied",
        },
    )
    assert resp.status_code == 200
    record = resp.json()
    assert record["cited_clause"] is None
    assert record["reason_code"] is None


def test_invalid_reason_code_rejected(client):
    _start(client)
    body = _inject(client)
    resp = client.post(
        "/api/overrides",
        json={
            "decision_id": body["decision_ids"][0],
            "override_type": "ESCALATE_TO_HUMAN",
            "operator_id": "op-bad",
            "reason": "nonsense code",
            "reason_code": "NOT_A_CODE",
        },
    )
    assert resp.status_code == 422


def test_audit_entry_carries_attribution(client):
    _start(client)
    body = _inject(client)
    resp = client.post(
        "/api/overrides",
        json={
            "decision_id": body["decision_ids"][0],
            "override_type": "DISMISS_INCIDENT",
            "operator_id": "op-audit",
            "reason": "duplicate report from trusted operator",
            "cited_clause": "POLICY_GAP",
            "reason_code": "POLICY_GAP",
        },
    )
    assert resp.status_code == 200
    entry = client.get("/api/audit?limit=1").json()["entries"][0]
    assert entry["action"] == "OVERRIDE_APPLIED"
    assert entry["cited_clause"] == "POLICY_GAP"
    assert entry["reason_code"] == "POLICY_GAP"
    assert entry["previous_hash"] != entry["entry_hash"]


def test_whatif_decision_has_lineage(client):
    _start(client)
    _inject(client, incident_type="flood", zone="east", severity="moderate")
    resp = client.post("/api/what-if/run", json={"scenario": "close_road"})
    assert resp.status_code == 200
    result = resp.json()
    assert result["live_state_mutated"] is False
    assert result["decision"]["lineage"] is not None
