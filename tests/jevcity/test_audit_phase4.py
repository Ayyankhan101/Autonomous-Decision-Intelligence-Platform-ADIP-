"""Phase 4 audit/override completion tests (plan §Phase 4 "New audit tests").

Route freeze, original-decision visibility after override, Laya status
audibility, guardrail/fallback metadata, override entries carrying the Laya
block, state-hash/questions-version linkage, chain integrity.
"""
from __future__ import annotations

from fastapi.routing import APIRoute

from jevcity.api.app import build_engine, create_app
from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
from jevcity.decision_engine.laya_adapter.questions import QUESTIONS_VERSION
from jevcity.schemas import (
    DecisionSource,
    IncidentType,
    LayaMode,
    LayaStatus,
    OverrideRequest,
    OverrideType,
    Priority,
    Zone,
)

FROZEN_ROUTES = {
    ("GET", "/api/state"),
    ("GET", "/api/incidents"),
    ("GET", "/api/incidents/{incident_id}"),
    ("GET", "/api/decisions"),
    ("GET", "/api/decisions/{decision_id}"),
    ("GET", "/api/resources"),
    ("GET", "/api/audit"),
    ("GET", "/api/what-if/{sandbox_id}/result"),
    ("POST", "/api/simulation/start"),
    ("POST", "/api/simulation/pause"),
    # Additive extension (plan §5.13 fixes pause/resume data loss); the 16
    # frozen endpoints above are unchanged. start() resets — resume() does not.
    ("POST", "/api/simulation/resume"),
    ("POST", "/api/simulation/reset"),
    ("POST", "/api/simulation/incident"),
    ("POST", "/api/simulation/bad-data"),
    ("POST", "/api/simulation/second-emergency"),
    ("POST", "/api/overrides"),
    ("POST", "/api/what-if/run"),
}


def _upstream(priority_choice: str) -> dict:
    dist = {k: 0.05 for k in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}
    dist[priority_choice] = 0.85
    return {
        "answers": {
            "priority": {"action": "priority", "choice": priority_choice,
                         "confidence": 0.9, "probabilities": dist, "type": "choice"},
            "needs_human_review": {"action": "auto", "confidence": 0.95,
                                    "noul": 0.05, "type": "review"},
            "recommended_resource_type": {"action": "resource", "choice": "ambulance",
                         "confidence": 0.9,
                         "probabilities": {"ambulance": 0.9, "police_unit": 0.1},
                         "type": "choice"},
        },
        "model": "fake-live",
        "usage": {"tokens": 1},
    }


def _live_engine(monkeypatch, upstream):
    engine = build_engine(mode=LayaMode.LIVE)
    if isinstance(upstream, Exception):
        def _boom(state):
            raise upstream
        monkeypatch.setattr(engine.adapter, "_live_call", _boom)
    else:
        monkeypatch.setattr(engine.adapter, "_live_call", lambda state: (upstream, 5.0))
    return engine


def _one_decision(engine):
    engine.simulation.start(42, 7)
    engine.simulation.inject_incident(IncidentType.ACCIDENT, Zone.NORTH)
    records = engine.process_pending()
    assert len(records) == 1
    return records[0]


def _audit_entries(engine, action: str):
    return [e for e in engine.audit.entries(limit=200) if e.action == action]


def test_route_set_is_frozen_and_audit_is_read_only():
    app = create_app(build_engine())
    routes = {
        (sorted(r.methods - {"HEAD", "OPTIONS"})[0], r.path)
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/")
    }
    assert routes == FROZEN_ROUTES
    audit_methods = {
        method for method, path in routes if "audit" in path
    }
    assert audit_methods == {"GET"}


def test_original_decision_visible_after_override(client):
    started = client.post(
        "/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7}
    )
    assert started.status_code == 200
    created = client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north"},
    )
    original_id = created.json()["decision_ids"][0]
    original = client.get(f"/api/decisions/{original_id}").json()

    overridden = client.post(
        "/api/overrides",
        json={"operator_id": "op-1", "decision_id": original_id,
              "override_type": "CHANGE_PRIORITY", "new_priority": "MEDIUM",
              "reason": "field report contradicts severity"},
    )
    assert overridden.status_code == 200
    assert overridden.json()["operator_id"] == "op-1"

    listed = client.get("/api/decisions").json()["decisions"]
    active = [d for d in listed if d["state"] == "OVERRIDE_ACTIVE"]
    assert len(active) == 1
    override_rec = active[0]
    assert override_rec["decision_id"] != original_id
    assert override_rec["override"]["operator_id"] == "op-1"
    assert override_rec["override"]["previous_priority"] == original["priority"]

    after = client.get(f"/api/decisions/{original_id}").json()
    assert after["state"] == original["state"]
    assert after["priority"] == original["priority"]
    assert after["override"] is None


def test_laya_timeout_and_invalid_response_are_auditable():
    for status in [LayaStatus.TIMEOUT, LayaStatus.INVALID_RESPONSE]:
        engine = build_engine()
        engine.adapter = LayaAdapter(mode=LayaMode.LIVE, force_status=status)
        record = _one_decision(engine)
        assert record.laya is not None and record.laya.status is status
        emitted = _audit_entries(engine, "DECISION_EMITTED")
        assert len(emitted) == 1
        meta = emitted[0].laya
        assert meta.laya_status is status
        assert meta.laya_fallback_used is True
        assert meta.laya_final_decision_source is DecisionSource.FALLBACK_RULE
        assert meta.laya_state_hash == record.laya.state_hash
        assert meta.laya_questions_version == QUESTIONS_VERSION
        engine.audit.close()


def test_guardrail_modified_and_fallback_metadata(monkeypatch):
    modified = _live_engine(monkeypatch, _upstream("MEDIUM"))
    record = _one_decision(modified)
    assert record.laya is not None
    assert record.laya.final_decision_source is DecisionSource.POLICY_FINALIZED
    entry = _audit_entries(modified, "DECISION_EMITTED")[0]
    assert entry.laya.laya_guardrail_modified is True
    assert entry.laya.laya_fallback_used is False
    assert entry.laya.laya_suggested_priority is Priority.MEDIUM
    assert entry.laya.laya_final_decision_source is DecisionSource.POLICY_FINALIZED
    assert entry.laya.laya_state_hash == record.laya.state_hash
    assert entry.laya.laya_questions_version == QUESTIONS_VERSION
    assert modified.audit.validate_chain() is True
    modified.audit.close()

    agreed = _live_engine(monkeypatch, _upstream("HIGH"))
    _one_decision(agreed)
    entry = _audit_entries(agreed, "DECISION_EMITTED")[0]
    assert entry.laya.laya_guardrail_modified is False
    assert entry.laya.laya_final_decision_source is DecisionSource.LAYA_PROPOSED
    agreed.audit.close()

    degraded = _live_engine(monkeypatch, RuntimeError("upstream down"))
    _one_decision(degraded)
    entry = _audit_entries(degraded, "DECISION_EMITTED")[0]
    assert entry.laya.laya_fallback_used is True
    assert entry.laya.laya_guardrail_modified is None
    assert entry.laya.laya_final_decision_source is DecisionSource.FALLBACK_RULE
    degraded.audit.close()


def test_human_override_after_laya_carries_laya_metadata(monkeypatch):
    engine = _live_engine(monkeypatch, _upstream("MEDIUM"))
    record = _one_decision(engine)
    override = engine.apply_override(
        OverrideRequest(
            operator_id="op-9",
            decision_id=record.decision_id,
            override_type=OverrideType.OVERRIDE_AUTOMATION_HOLD,
            reason="incident commander assumes control",
        )
    )
    entries = _audit_entries(engine, "OVERRIDE_APPLIED")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.actor == "op-9"
    assert entry.reason == "incident commander assumes control"
    assert entry.decision_id == record.decision_id
    meta = entry.laya
    assert meta.laya_checkpoint == record.laya.checkpoint
    assert meta.laya_state_hash == record.laya.state_hash
    assert meta.laya_questions_version == QUESTIONS_VERSION
    assert meta.laya_final_decision_source is DecisionSource.POLICY_FINALIZED
    assert engine.audit.validate_chain() is True
    assert override.state.value == "OVERRIDE_ACTIVE"
    engine.audit.close()
