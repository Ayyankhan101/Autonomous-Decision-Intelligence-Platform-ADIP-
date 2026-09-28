from __future__ import annotations

from jevcity.decision_engine.guardrail.allocate import (
    FALLBACK_RESOURCE,
    allocate_for_incident,
    order_queue,
)
from jevcity.schemas import (
    DecisionRecord,
    IncidentType,
    Priority,
    ResourceType,
    Zone,
)
from jevcity.simulation.resource_pool import ResourcePool
from datetime import UTC, datetime

from model_stubs import FixedSeverity, FixedTraffic

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def test_allocates_same_zone_first():
    pool = ResourcePool.default()
    result = allocate_for_incident(
        pool,
        incident_id="inc-1",
        zone=Zone.NORTH,
        incident_type=IncidentType.ACCIDENT,
        priority=Priority.HIGH,
        recommended=[ResourceType.AMBULANCE],
    )
    assert result.assigned_ids == ["amb-01"]  # north ambulance
    assert pool.get("amb-01").assigned_incident_id == "inc-1"


def test_contention_when_no_resource_available():
    pool = ResourcePool.default()
    for r in pool.all():
        if r.type == ResourceType.AMBULANCE:
            pool.take_offline(r.resource_id)
    result = allocate_for_incident(
        pool,
        incident_id="inc-2",
        zone=Zone.SOUTH,
        incident_type=IncidentType.ACCIDENT,
        priority=Priority.HIGH,
        recommended=[ResourceType.AMBULANCE],
    )
    assert result.contention is True
    assert result.assigned_ids == []


def test_contention_escalation_state_not_false_success(engine):
    from jevcity.schemas import SeverityHint

    engine.severity = FixedSeverity("MEDIUM", 0.9)
    engine.traffic = FixedTraffic(0.3, 0.9)
    # flood: remove flood units + police fallback; ambulances stay available so the
    # mock Laya review gate (driven by ambulance availability) does not preempt
    for r in engine.simulation.pool.all():
        if r.type in (ResourceType.FLOOD_RESPONSE_UNIT, ResourceType.POLICE_UNIT):
            engine.simulation.pool.take_offline(r.resource_id)
    engine.simulation.inject_incident(
        IncidentType.FLOOD, Zone.EAST, SeverityHint.MODERATE
    )
    record = engine.process_pending()[-1]
    assert record.state.value == "CONTENTION_ESCALATION"
    assert "R-CONTENTION-ESCALATE-01" in record.matched_rules
    assert record.assigned_resource_ids == []  # no fake success


def test_greedy_order_priority_confidence_waiting():
    def rec(pid, conf, t):
        return DecisionRecord.model_construct(
            decision_id=pid,
            priority=Priority.CRITICAL if conf == 0.9 else Priority.MEDIUM,
            overall_confidence=conf,
            decision_time_simulated=t,
        )

    a = rec("a", 0.9, datetime(2026, 9, 27, 10, 0, tzinfo=UTC))
    b = rec("b", 0.9, datetime(2026, 9, 27, 9, 0, tzinfo=UTC))
    c = rec("c", 0.5, datetime(2026, 9, 27, 8, 0, tzinfo=UTC))
    ordered = order_queue([a, b, c])
    # equal priority+confidence → earlier wait first; higher confidence first
    assert [r.decision_id for r in ordered] == ["b", "a", "c"]


def test_fallback_resource_map_covers_all_incident_types():
    for itype in IncidentType:
        assert itype in FALLBACK_RESOURCE
        assert FALLBACK_RESOURCE[itype]
