from __future__ import annotations

from jevcity.schemas import (
    IncidentType,
    ResourceType,
    SeverityHint,
    WhatIfRequest,
    WhatIfScenario,
    Zone,
)


from model_stubs import FixedSeverity, FixedTraffic


def _seed_incident(engine):
    engine.severity = FixedSeverity("HIGH", 0.9)
    engine.traffic = FixedTraffic(0.5, 0.9)
    incident_id = engine.simulation.inject_incident(
        IncidentType.ACCIDENT, Zone.NORTH, SeverityHint.SEVERE
    )
    engine.process_pending()
    return incident_id


def test_what_if_never_writes_live_audit(engine):
    _seed_incident(engine)
    before = len(engine.audit.entries(limit=1000))
    result = engine.run_what_if(
        WhatIfRequest(scenario=WhatIfScenario.REMOVE_ONE_AMBULANCE)
    )
    after = len(engine.audit.entries(limit=1000))
    assert after == before
    assert result.audit_written is False
    assert result.dry_run is True
    assert result.decision.dry_run is True
    assert engine.audit.validate_chain() is True


def test_what_if_never_mutates_live_state(engine):
    _seed_incident(engine)
    live_ambulances = engine.simulation.pool.available_count(ResourceType.AMBULANCE)
    live_decisions = len(engine.decisions)
    live_incidents = set(engine.simulation.incidents)
    result = engine.run_what_if(
        WhatIfRequest(scenario=WhatIfScenario.REMOVE_ONE_AMBULANCE)
    )
    assert result.live_state_mutated is False
    assert engine.simulation.pool.available_count(ResourceType.AMBULANCE) == live_ambulances
    assert len(engine.decisions) == live_decisions
    assert set(engine.simulation.incidents) == live_incidents


def test_what_if_remove_ambulance_changes_outcome(engine):
    _seed_incident(engine)
    # drain the whole live fleet in the sandbox scenario by removing one ambulance
    # when none are available → sandbox decision reflects contention
    for r in engine.simulation.pool.all():
        if r.type == ResourceType.AMBULANCE:
            engine.simulation.pool.take_offline(r.resource_id)
    live_result = engine.run_what_if(
        WhatIfRequest(scenario=WhatIfScenario.REMOVE_ONE_AMBULANCE)
    )
    assert live_result.decision.state.value in (
        "CONTENTION_ESCALATION", "HOLD_FOR_HUMAN", "MODEL_DEGRADED",
    )
    # restore for other tests (engine fixture is function-scoped anyway)
    for r in engine.simulation.pool.all():
        if r.type == ResourceType.AMBULANCE:
            engine.simulation.pool.release(r.resource_id)


def test_what_if_uses_isolated_laya_cache(engine):
    _seed_incident(engine)
    result = engine.run_what_if(
        WhatIfRequest(scenario=WhatIfScenario.CLOSE_ROAD)
    )
    assert result.laya_mode == "mock"
    assert result.decision.laya is not None


def test_what_if_second_emergency_leaves_no_trace(engine):
    _seed_incident(engine)
    before_events = len(engine.simulation.raw_events)
    before_incidents = set(engine.simulation.incidents)
    result = engine.run_what_if(
        WhatIfRequest(scenario=WhatIfScenario.SECOND_EMERGENCY)
    )
    assert result.decision.dry_run is True
    assert len(engine.simulation.raw_events) == before_events
    assert set(engine.simulation.incidents) == before_incidents


def test_what_if_skips_hard_rejected_latest_incident(engine):
    """Regression: rejected incidents have no parsed reports — What-If must pick a
    decidable incident instead of 500ing (found by live server run)."""
    from jevcity.schemas import InjectionMode

    _seed_incident(engine)
    engine.simulation.inject_incident(
        IncidentType.FLOOD, Zone.EAST, bad_data_mode=InjectionMode.OUT_OF_RANGE
    )
    engine.process_pending()
    result = engine.run_what_if(
        WhatIfRequest(scenario=WhatIfScenario.CLOSE_ROAD)
    )
    assert result.decision.dry_run is True
    assert result.decision.state.value != "REJECTED_INPUT"
