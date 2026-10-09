"""Enhancement 4: zero-trust override friction — tier classification, gating, audit."""
from __future__ import annotations

from jevcity.schemas import (
    ImpactTier,
    OverrideContextCode,
    OverrideType,
    Priority,
)


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


def test_break_glass_tier_on_life_safety_raise(client):
    _start(client)
    body = _inject(client, incident_type="accident", severity="severe")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides/impact",
        json={"decision_id": did, "override_type": "CHANGE_PRIORITY",
              "new_priority": "CRITICAL"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["tier"] == "BREAK_GLASS"
    assert out["requires_break_glass"] is True
    assert out["requires_ack"] is True
    assert "BROKEN" not in out["warning"]  # sanity: warning is prose, not traceback
    assert out["projected"]["life_safety"] is True
    assert out["projected"]["priority_to"] == "CRITICAL"


def test_high_tier_on_non_life_safety_raise(client):
    _start(client)
    body = _inject(client, incident_type="flood", zone="east", severity="moderate")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides/impact",
        json={"decision_id": did, "override_type": "CHANGE_PRIORITY",
              "new_priority": "CRITICAL"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["tier"] == "HIGH"
    assert out["requires_context_code"] is True
    assert out["requires_break_glass"] is False
    assert out["requires_ack"] is True


def test_low_tier_on_data_quality_override(client):
    _start(client)
    body = _inject(client, incident_type="flood", zone="east", severity="moderate")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides/impact",
        json={"decision_id": did, "override_type": "MARK_DATA_UNTRUSTED"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["tier"] == "LOW"
    assert out["requires_ack"] is False
    assert out["requires_context_code"] is False
    assert out["requires_break_glass"] is False


def test_break_glass_requires_flag(client):
    _start(client)
    body = _inject(client, incident_type="accident", severity="severe")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": did,
              "override_type": "CHANGE_PRIORITY", "reason": "raise without flag",
              "new_priority": "CRITICAL"},
    )
    assert r.status_code == 422
    assert "break_glass" in r.json()["detail"]
    r2 = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": did,
              "override_type": "CHANGE_PRIORITY", "reason": "raise with flag",
              "new_priority": "CRITICAL", "break_glass": True},
    )
    assert r2.status_code == 200
    assert r2.json()["impact_tier"] == "BREAK_GLASS"
    assert r2.json()["break_glass"] is True


def test_high_tier_requires_ack_and_context_code(client):
    _start(client)
    body = _inject(client, incident_type="flood", zone="east", severity="moderate")
    did = body["decision_ids"][0]
    base = {"operator_id": "op-1", "decision_id": did,
            "override_type": "CHANGE_PRIORITY", "reason": "raise", "new_priority": "CRITICAL"}
    r = client.post("/api/overrides", json=base)
    assert r.status_code == 422
    assert "context_code" in r.json()["detail"]
    r = client.post("/api/overrides", json={**base, "impact_ack": True})
    assert r.status_code == 422
    r = client.post(
        "/api/overrides",
        json={**base, "impact_ack": True, "context_code": "SCENE_REPORT"},
    )
    assert r.status_code == 200
    assert r.json()["impact_tier"] == "HIGH"
    assert r.json()["context_code"] == "SCENE_REPORT"


def test_dismiss_with_assigned_units_is_high(client):
    _start(client)
    body = _inject(client, incident_type="fire", zone="south", severity="severe")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides/impact",
        json={"decision_id": did, "override_type": "DISMISS_INCIDENT"},
    )
    assert r.status_code == 200
    assert r.json()["tier"] == "HIGH"
    assert "releases" in r.json()["warning"]


def test_low_tier_override_needs_no_extra_fields(client):
    _start(client)
    body = _inject(client, incident_type="flood", zone="east", severity="moderate")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": did,
              "override_type": "MARK_DATA_UNTRUSTED", "reason": "sensor drift seen"},
    )
    assert r.status_code == 200
    assert r.json()["impact_tier"] == "LOW"


def test_preview_is_read_only(client):
    _start(client)
    body = _inject(client, incident_type="accident", severity="severe")
    did = body["decision_ids"][0]
    before_audit = len(client.get("/api/audit?limit=1000").json()["entries"])
    before_state = client.get(f"/api/decisions/{did}").json()["state"]
    for _ in range(3):
        r = client.post(
            "/api/overrides/impact",
            json={"decision_id": did, "override_type": "CHANGE_PRIORITY",
                  "new_priority": "CRITICAL"},
        )
        assert r.status_code == 200
    assert len(client.get("/api/audit?limit=1000").json()["entries"]) == before_audit
    assert client.get(f"/api/decisions/{did}").json()["state"] == before_state
    assert before_state == "AUTO_APPROVED"


def test_preview_unknown_decision_404(client):
    _start(client)
    r = client.post(
        "/api/overrides/impact",
        json={"decision_id": "dec-nope", "override_type": "MARK_DATA_UNTRUSTED"},
    )
    assert r.status_code == 404


def test_context_code_enum_enforced(client):
    _start(client)
    body = _inject(client, incident_type="flood", zone="east", severity="moderate")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": did,
              "override_type": "CHANGE_PRIORITY", "reason": "raise",
              "new_priority": "CRITICAL", "impact_ack": True,
              "context_code": "MADE_UP_CODE"},
    )
    assert r.status_code == 422


def test_priority_lower_than_raise_is_low(client):
    _start(client)
    body = _inject(client, incident_type="accident", severity="severe")
    did = body["decision_ids"][0]
    current = client.get(f"/api/decisions/{did}").json()["priority"]
    lower = {Priority.LOW: None, Priority.MEDIUM: Priority.LOW,
             Priority.HIGH: Priority.MEDIUM, Priority.CRITICAL: Priority.HIGH}[Priority(current)]
    if lower is None:
        return  # already LOW: nothing to lower to
    r = client.post(
        "/api/overrides/impact",
        json={"decision_id": did, "override_type": "CHANGE_PRIORITY",
              "new_priority": lower.value},
    )
    assert r.status_code == 200
    assert r.json()["tier"] == "LOW"


def test_audit_entry_carries_impact_fields(client):
    _start(client)
    body = _inject(client, incident_type="accident", severity="severe")
    did = body["decision_ids"][0]
    r = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": did,
              "override_type": "CHANGE_PRIORITY", "reason": "post-event review flag",
              "new_priority": "CRITICAL", "break_glass": True,
              "cited_clause": "POL-7.3", "reason_code": "POLICY_CLAUSE"},
    )
    assert r.status_code == 200
    entry = client.get("/api/audit?limit=1").json()["entries"][0]
    assert entry["action"] == "OVERRIDE_APPLIED"
    assert entry["impact_tier"] == "BREAK_GLASS"
    assert entry["break_glass"] is True
    assert entry["cited_clause"] == "POL-7.3"
    assert client.get("/api/audit").json()["entries"][0]["entry_hash"]


def test_impact_tier_types_and_enums():
    assert ImpactTier.LOW.value == "LOW"
    assert ImpactTier.HIGH.value == "HIGH"
    assert ImpactTier.BREAK_GLASS.value == "BREAK_GLASS"
    assert OverrideContextCode.ROAD_CONDITION.value == "ROAD_CONDITION"
    assert OverrideType.DISMISS_INCIDENT.value == "DISMISS_INCIDENT"
