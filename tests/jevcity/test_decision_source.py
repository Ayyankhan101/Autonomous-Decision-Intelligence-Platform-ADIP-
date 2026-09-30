"""Decision-source live path (Phase 3 C8): every Laya outcome has one explicit source.

Engine runs the LIVE adapter with a monkeypatched `_live_call` (no checkpoint
load), so the full C5 path — retry gate, breaker, to_raw, normalize, policy —
executes; only the upstream predict payload is faked. Seed 42/7 + ACCIDENT/NORTH
yields final priority HIGH under every fake (INV-5 downgrade, verified).
"""
from __future__ import annotations


from jevcity.api.app import build_engine
from jevcity.schemas import (
    DecisionSource,
    DecisionState,
    IncidentType,
    InjectionMode,
    LayaMode,
    POLICY_VERSION,
    Zone,
)


def _upstream(priority_choice: str, *, noul: float = 0.05) -> dict:
    dist = {k: 0.05 for k in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}
    dist[priority_choice] = 0.85
    return {
        "answers": {
            "priority": {
                "action": "priority",
                "choice": priority_choice,
                "confidence": 0.9,
                "probabilities": dist,
                "type": "choice",
            },
            "needs_human_review": {
                "action": "review" if noul >= 0.5 else "auto",
                "confidence": max(noul, 1.0 - noul),
                "noul": noul,
                "type": "review",
            },
            "recommended_resource_type": {
                "action": "resource",
                "choice": "ambulance",
                "confidence": 0.9,
                "probabilities": {"ambulance": 0.9, "police_unit": 0.1},
                "type": "choice",
            },
        },
        "model": "fake-live",
        "usage": {"tokens": 1},
    }


def _run(monkeypatch, upstream):
    engine = build_engine(mode=LayaMode.LIVE)
    if isinstance(upstream, Exception):
        def _boom(state):
            raise upstream
        monkeypatch.setattr(engine.adapter, "_live_call", _boom)
    else:
        monkeypatch.setattr(
            engine.adapter, "_live_call", lambda state: (upstream, 5.0)
        )
    engine.simulation.start(42, 7)
    engine.simulation.inject_incident(IncidentType.ACCIDENT, Zone.NORTH)
    records = engine.process_pending()
    engine.audit.close()
    assert len(records) == 1
    return records[0]


def test_matching_suggestion_yields_laya_proposed(monkeypatch):
    record = _run(monkeypatch, _upstream("HIGH"))
    assert record.state is DecisionState.AUTO_APPROVED
    assert record.priority.value == "HIGH"
    assert record.laya is not None
    assert record.laya.final_decision_source is DecisionSource.LAYA_PROPOSED
    assert record.policy_version == POLICY_VERSION


def test_modified_suggestion_yields_policy_finalized(monkeypatch):
    record = _run(monkeypatch, _upstream("MEDIUM"))
    assert record.state is DecisionState.AUTO_APPROVED
    assert record.priority.value == "HIGH"
    assert record.laya is not None
    assert record.laya.final_decision_source is DecisionSource.POLICY_FINALIZED


def test_live_failure_yields_fallback_rule(monkeypatch):
    record = _run(monkeypatch, RuntimeError("upstream down"))
    assert record.state is DecisionState.MODEL_DEGRADED
    assert record.laya is not None
    assert record.laya.status.value == "unavailable"
    assert record.laya.final_decision_source is DecisionSource.FALLBACK_RULE
    assert "R-LAYA-MODEL-DEGRADED-01" in record.matched_rules


def test_laya_review_request_yields_human_required(monkeypatch):
    record = _run(monkeypatch, _upstream("HIGH", noul=0.9))
    assert record.state is DecisionState.HOLD_FOR_HUMAN
    assert record.laya is not None
    assert record.laya.suggested_needs_human_review is True
    assert record.laya.final_decision_source is DecisionSource.HUMAN_REQUIRED
    assert "R-LAYA-HUMAN-REVIEW-SUGGESTED-01" in record.matched_rules


def test_hard_rejected_input_never_reaches_laya(monkeypatch):
    engine = build_engine(mode=LayaMode.LIVE)
    seen: list = []

    def _spy(state):
        seen.append(state)
        return _upstream("HIGH"), 5.0

    monkeypatch.setattr(engine.adapter, "_live_call", _spy)
    engine.simulation.start(42, 7)
    engine.simulation.inject_incident(
        IncidentType.ACCIDENT, Zone.NORTH, bad_data_mode=InjectionMode.MISSING_FIELDS
    )
    records = engine.process_pending()
    engine.audit.close()
    assert len(records) == 1
    assert records[0].state is DecisionState.REJECTED_INPUT
    assert records[0].laya is None
    assert seen == []
    assert records[0].policy_version == POLICY_VERSION
