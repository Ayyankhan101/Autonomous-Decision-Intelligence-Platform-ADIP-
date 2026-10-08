"""Property tests for plan §3.3 policy invariants 1-5 and 9-16."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jevcity.decision_engine.guardrail import confidence as conf
from jevcity.decision_engine.guardrail.policy import DecisionContext, decide
from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
from jevcity.decision_engine.laya_adapter.state_builder import build_state
from jevcity.models.anomaly import AnomalyDetector
from jevcity.schemas import (
    AnomalyOutput,
    DecisionState,
    IncidentLifecycle,
    IncidentRecord,
    IncidentType,
    LayaMode,
    LayaStatus,
    ModelStatus,
    NormalizedLayaResponse,
    Priority,
    ValidationResult,
    ValidationStatus,
    Zone,
)
from jevcity.simulation.resource_pool import ResourcePool
from jevcity.simulation.state import SimulationState
from jevcity.features.engineer import build_features

from model_stubs import FixedSeverity, FixedTraffic

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _incident() -> IncidentRecord:
    return IncidentRecord(
        incident_id="inc-1",
        incident_type=IncidentType.ACCIDENT,
        zone=Zone.NORTH,
        lifecycle=IncidentLifecycle.VALIDATED,
        first_seen_simulated=NOW,
        latest_simulated=NOW,
        report_count=1,
    )


def _validation(status=ValidationStatus.VALID, score=0.05) -> ValidationResult:
    return ValidationResult(
        event_id="evt-1",
        incident_id="inc-1",
        validation_status=status,
        data_quality_score=score,
    )


def _ctx(
    *,
    severity: FixedSeverity,
    traffic: FixedTraffic,
    anomaly: AnomalyOutput,
    laya: NormalizedLayaResponse | None = None,
    validation: ValidationResult | None = None,
    pool: ResourcePool | None = None,
    contradictions: list[str] | None = None,
) -> DecisionContext:
    if laya is None:
        adapter = LayaAdapter(mode=LayaMode.MOCK)
        laya = adapter.ask(_demo_state(severity, traffic, anomaly))
    return DecisionContext(
        incident=_incident(),
        validation=validation or _validation(),
        severity=severity.predict({}),
        traffic=traffic.predict({}),
        anomaly=anomaly,
        contradictions=contradictions or [],
        laya=laya,
        pool=pool or ResourcePool.default(),
        now=NOW,
        decision_id="dec-test",
    )


def _demo_state(severity, traffic, anomaly) -> "object":
    sim = SimulationState()
    event = sim.generator.make_incident(
        IncidentType.ACCIDENT, Zone.NORTH,
        when=datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
    )
    reports = [event]
    features = build_features(reports)
    sev_out = severity.predict(features)
    tr_out = traffic.predict(features)
    return build_state(
        incident_id="inc-1",
        primary=event,
        features=features,
        severity=sev_out,
        traffic=tr_out,
        anomaly=anomaly,
        available_ambulances=3,
        active_competing_incidents=0,
    )


def _ok_anomaly(score=0.05, dq_anomaly=False, situational=False, reasons=None) -> AnomalyOutput:
    return AnomalyOutput(
        data_quality_anomaly=dq_anomaly,
        data_quality_score=score,
        situational_anomaly=situational,
        reasons=reasons or [],
    )


# --- Invariant 1: hard invalid input --------------------------------


def test_inv1_hard_invalid_never_auto_decides():
    record = decide(
        _ctx(
            severity=FixedSeverity("CRITICAL", 0.9),
            traffic=FixedTraffic(0.9, 0.9),
            anomaly=_ok_anomaly(),
            validation=_validation(ValidationStatus.HARD_REJECTED, 1.0),
        )
    )
    assert record.state == DecisionState.REJECTED_INPUT
    assert record.priority == Priority.LOW
    assert record.matched_rules == ["R-INPUT-REJECT-01"]


# --- Invariant 2: dq anomaly cannot produce CRITICAL without human ---


def test_inv2_dq_anomaly_blocks_critical_auto():
    record = decide(
        _ctx(
            severity=FixedSeverity("CRITICAL", 0.9),
            traffic=FixedTraffic(0.9, 0.9),
            anomaly=_ok_anomaly(
                score=0.6, dq_anomaly=True,
                reasons=["contradictory_reports"],
            ),
        )
    )
    assert not (record.priority == Priority.CRITICAL
                and record.state == DecisionState.AUTO_APPROVED)
    assert record.state == DecisionState.HOLD_FOR_HUMAN
    assert "R-DATA-QUALITY-HOLD-01" in record.matched_rules


# --- Invariant 3: low confidence cannot auto-decide ------------------


def test_inv3_low_confidence_holds():
    record = decide(
        _ctx(
            severity=FixedSeverity("HIGH", 0.3),
            traffic=FixedTraffic(0.4, 0.3),
            anomaly=_ok_anomaly(score=0.9),
        )
    )
    assert record.state == DecisionState.HOLD_FOR_HUMAN
    assert "R-LOW-CONFIDENCE-HOLD-01" in record.matched_rules


# --- Invariant 4: model failure cannot auto-decide -------------------


@pytest.mark.parametrize("status", [ModelStatus.ERROR, ModelStatus.TIMEOUT])
def test_inv4_model_failure_degrades(status):
    record = decide(
        _ctx(
            severity=FixedSeverity("HIGH", 0.9, status=status),
            traffic=FixedTraffic(0.5, 0.9),
            anomaly=_ok_anomaly(),
        )
    )
    assert record.state == DecisionState.MODEL_DEGRADED
    assert record.state != DecisionState.AUTO_APPROVED


def test_inv4_anomaly_failure_fails_closed():
    detector = AnomalyDetector(fail=ModelStatus.ERROR)
    output = detector.predict({}, [], _validation(), [])
    assert output.data_quality_anomaly is True
    assert output.data_quality_score == 1.0
    assert "anomaly_model_failure" in output.reasons


# --- Invariant 5: CRITICAL requires two independent signals -----------


def test_inv5_single_signal_cannot_critical():
    record = decide(
        _ctx(
            severity=FixedSeverity("CRITICAL", 0.95),
            traffic=FixedTraffic(0.2, 0.9),  # not crossed (<0.6)
            anomaly=_ok_anomaly(situational=False),
        )
    )
    assert record.priority != Priority.CRITICAL
    assert "R-INV-5-CRITICAL-NEEDS-TWO-SIGNALS-01" in record.matched_rules


def test_inv5_two_signals_allow_critical():
    record = decide(
        _ctx(
            severity=FixedSeverity("CRITICAL", 0.95),
            traffic=FixedTraffic(0.9, 0.9),
            anomaly=_ok_anomaly(),
        )
    )
    assert record.priority == Priority.CRITICAL


# --- Invariant 9/10: Laya cannot bypass or force CRITICAL ------------


def test_inv10_laya_alone_cannot_force_critical():
    """Laya suggests CRITICAL; only one upstream signal supports it."""
    severity = FixedSeverity("MEDIUM", 0.9)
    traffic = FixedTraffic(0.1, 0.9)
    anomaly = _ok_anomaly()
    laya = LayaAdapter(mode=LayaMode.MOCK).ask(
        _demo_state(severity, traffic, anomaly)
    )
    # force Laya to suggest CRITICAL via canned cache response
    laya = _canned_laya(laya, priority="CRITICAL", ac=0.95, review=False)
    record = decide(
        _ctx(severity=severity, traffic=traffic, anomaly=anomaly, laya=laya)
    )
    assert record.priority != Priority.CRITICAL
    assert "R-LAYA-CRITICAL-BLOCKED-INSUFFICIENT-SIGNALS-01" in record.matched_rules
    # laya block records suggestion separately from final priority (Key Rule)
    assert record.laya.suggested_priority == Priority.CRITICAL
    assert record.priority != record.laya.suggested_priority


def test_inv9_laya_invalid_fails_closed():
    laya = NormalizedLayaResponse.failed(
        LayaStatus.INVALID_RESPONSE,
        runtime="test", checkpoint="cp", router_model="rm", device="cpu",
        state_hash="sha256:x", questions_hash="sha256:y", error_code="bad_choice",
    )
    record = decide(
        _ctx(
            severity=FixedSeverity("HIGH", 0.9),
            traffic=FixedTraffic(0.5, 0.9),
            anomaly=_ok_anomaly(),
            laya=laya,
        )
    )
    assert record.state in (DecisionState.MODEL_DEGRADED, DecisionState.HOLD_FOR_HUMAN)
    assert record.laya.status == LayaStatus.INVALID_RESPONSE


def test_inv12_laya_timeout_falls_back_to_policy():
    laya = NormalizedLayaResponse.failed(
        LayaStatus.TIMEOUT,
        runtime="test", checkpoint="cp", router_model="rm", device="cpu",
        state_hash="sha256:x", questions_hash="sha256:y", error_code="timeout",
    )
    record = decide(
        _ctx(
            severity=FixedSeverity("MEDIUM", 0.9),
            traffic=FixedTraffic(0.3, 0.9),
            anomaly=_ok_anomaly(),
            laya=laya,
        )
    )
    assert record.state == DecisionState.MODEL_DEGRADED
    assert "R-LAYA-FALLBACK-POLICY-ONLY-01" in record.matched_rules
    assert record.priority == Priority.MEDIUM  # policy decided without Laya


def test_laya_low_answer_confidence_holds():
    sim_laya = LayaAdapter(mode=LayaMode.MOCK).ask(
        _demo_state(FixedSeverity("MEDIUM", 0.9), FixedTraffic(0.3, 0.9), _ok_anomaly())
    )
    laya = _canned_laya(sim_laya, priority="MEDIUM", ac=0.2, review=False)
    record = decide(
        _ctx(
            severity=FixedSeverity("MEDIUM", 0.9),
            traffic=FixedTraffic(0.3, 0.9),
            anomaly=_ok_anomaly(),
            laya=laya,
        )
    )
    assert record.state == DecisionState.HOLD_FOR_HUMAN
    assert "R-LAYA-LOW-ANSWER-CONFIDENCE-01" in record.matched_rules


def test_laya_review_suggestion_holds():
    sim_laya = LayaAdapter(mode=LayaMode.MOCK).ask(
        _demo_state(FixedSeverity("MEDIUM", 0.9), FixedTraffic(0.3, 0.9), _ok_anomaly())
    )
    laya = _canned_laya(sim_laya, priority="MEDIUM", ac=0.9, review=True)
    record = decide(
        _ctx(
            severity=FixedSeverity("MEDIUM", 0.9),
            traffic=FixedTraffic(0.3, 0.9),
            anomaly=_ok_anomaly(),
            laya=laya,
        )
    )
    assert record.state == DecisionState.HOLD_FOR_HUMAN
    assert "R-LAYA-HUMAN-REVIEW-SUGGESTED-01" in record.matched_rules


# --- Plan §6 guardrail scenario battery --------------------------------
# Six scenarios (plan Phase 6): (1) Laya CRITICAL with one supporting signal -> blocked
# (test_inv10_laya_alone_cannot_force_critical); (2) AUTO_APPROVED low answer confidence
# -> HOLD (test_laya_low_answer_confidence_holds); (3) Laya ignores a data-quality
# anomaly -> guardrail overrides (below); (4) Laya recommends an unavailable resource ->
# allocator corrects instead of false success (below); (5) Laya contradicts the rules ->
# rules win (test_inv5_* / test_inv9_laya_invalid_fails_closed); (6) Laya proposes an
# action from adversarial text -> policy ignores the text (test_notes_never_reach_state_or_render,
# test_adversarial_notes_flagged_not_followed in test_simulation.py).


def test_plan6_laya_ignores_dq_anomaly_guardrail_overrides():
    """Scenario (3): Laya confidently suggests CRITICAL while the data-quality model
    reports an anomaly — the guardrail holds for human review instead of auto-acting."""
    sim_laya = LayaAdapter(mode=LayaMode.MOCK).ask(
        _demo_state(FixedSeverity("CRITICAL", 0.95), FixedTraffic(0.9, 0.9), _ok_anomaly())
    )
    laya = _canned_laya(sim_laya, priority="CRITICAL", ac=0.95, review=False)
    record = decide(
        _ctx(
            severity=FixedSeverity("CRITICAL", 0.95),
            traffic=FixedTraffic(0.9, 0.9),
            anomaly=_ok_anomaly(
                score=0.6, dq_anomaly=True, reasons=["contradictory_reports"]
            ),
            laya=laya,
        )
    )
    assert record.state == DecisionState.HOLD_FOR_HUMAN
    assert record.state != DecisionState.AUTO_APPROVED
    assert "R-DATA-QUALITY-HOLD-01" in record.matched_rules
    assert record.laya.suggested_priority == Priority.CRITICAL


def test_plan6_laya_unavailable_resource_allocator_escalates(engine):
    """Scenario (4): Laya recommends a fire truck but every fire truck is offline —
    the allocator must not report a fake successful assignment; it escalates contention."""
    from jevcity.schemas import ResourceType, SeverityHint

    engine.severity = FixedSeverity("HIGH", 0.95)
    engine.traffic = FixedTraffic(0.7, 0.95)
    for r in engine.simulation.pool.all():
        if r.type == ResourceType.FIRE_TRUCK:
            engine.simulation.pool.take_offline(r.resource_id)
    engine.simulation.inject_incident(
        IncidentType.FIRE, Zone.SOUTH, SeverityHint.SEVERE
    )
    record = engine.process_pending()[-1]
    assert record.state == DecisionState.CONTENTION_ESCALATION
    assert "R-CONTENTION-ESCALATE-01" in record.matched_rules
    assert record.assigned_resource_ids == []
    assert record.laya.recommended_resource_type == ResourceType.FIRE_TRUCK


# --- §5.8 dual confidence contract ------------------------------------


def test_overall_confidence_excludes_laya():
    """Laya answer_confidence never enters the min() — separate gate only."""
    value = conf.overall_confidence(0.9, 0.9, data_quality_score=0.1)
    assert value == pytest.approx(0.9)
    # inverting dq: high badness drags overall down
    assert conf.overall_confidence(0.9, 0.9, 0.9) == pytest.approx(0.1)


def test_laya_not_counted_as_independent_signal():
    count = conf.critical_signal_count(
        severity_crossed=True, traffic_crossed=False, situational_anomaly=False
    )
    assert count == 1  # no laya parameter exists — structurally ineligible


# --- helpers -----------------------------------------------------------


def _canned_laya(base, *, priority: str, ac: float, review: bool) -> NormalizedLayaResponse:
    from jevcity.schemas import ChoiceAnswer, NoulAnswer

    return base.model_copy(
        update={
            "answers": {
                "priority": ChoiceAnswer(
                    choice=priority,
                    confidence=ac,
                    answer_confidence=ac,
                    distribution={priority: ac},
                ),
                "needs_human_review": NoulAnswer(noul=0.9 if review else 0.1,
                                                 answer_confidence=0.9),
                "recommended_resource_type": ChoiceAnswer(
                    choice="ambulance", confidence=0.9, answer_confidence=0.9,
                    distribution={"ambulance": 0.9},
                ),
            },
            "status": LayaStatus.OK,
        }
    )
