"""LayaBlock.distribution plumbing (Phase 5 plan: probability distribution UI).

Runs the LIVE adapter with a monkeypatched `_live_call` (no checkpoint load);
only the upstream predict payload is faked, so to_raw → normalize → policy
execute for real. Asserts the normalized priority distribution lands on the
decision's Laya block for dashboard consumption.
"""
from __future__ import annotations

from jevcity.api.app import build_engine
from jevcity.schemas import IncidentType, LayaMode, Zone

_DIST = {"LOW": 0.05, "MEDIUM": 0.10, "HIGH": 0.65, "CRITICAL": 0.20}


def _upstream(state):
    return (
        {
            "answers": {
                "priority": {
                    "action": "priority",
                    "choice": "HIGH",
                    "confidence": 0.9,
                    "probabilities": dict(_DIST),
                    "type": "choice",
                },
                "needs_human_review": {
                    "action": "auto",
                    "confidence": 0.95,
                    "noul": 0.05,
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
        },
        5.0,
    )


def test_laya_block_carries_priority_distribution(monkeypatch):
    engine = build_engine(mode=LayaMode.LIVE)
    monkeypatch.setattr(engine.adapter, "_live_call", _upstream)
    engine.simulation.start(42, 7)
    engine.simulation.inject_incident(IncidentType.ACCIDENT, Zone.NORTH)
    record = engine.process_pending()[-1]

    assert record.laya is not None
    assert record.laya.status.value == "ok"
    assert record.laya.distribution == _DIST
    assert abs(sum(record.laya.distribution.values()) - 1.0) < 1e-9


def test_laya_block_distribution_empty_on_failure(monkeypatch):
    engine = build_engine(mode=LayaMode.LIVE)

    def _boom(state):
        raise TimeoutError("forced")

    monkeypatch.setattr(engine.adapter, "_live_call", _boom)
    engine.simulation.start(42, 7)
    engine.simulation.inject_incident(IncidentType.FIRE, Zone.SOUTH)
    record = engine.process_pending()[-1]

    assert record.laya is not None
    assert record.laya.distribution == {}
    assert record.state.value != "REJECTED_INPUT"
