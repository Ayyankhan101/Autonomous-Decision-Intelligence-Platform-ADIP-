"""Deterministic policy guardrail — final authority (plan §3.3, §5.4).

Order of authority: schema validation → confidence/data-quality/independence gates →
Laya advisory (never final) → allocation → decision record. Laya can suggest; policy decides.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from jevcity.schemas import (
    AnomalyOutput,
    DecisionRecord,
    DecisionSource,
    DecisionState,
    IncidentRecord,
    LayaMode,
    LayaStatus,
    ModelOutput,
    ModelStatus,
    NormalizedLayaResponse,
    PolicyPosition,
    Priority,
    SeveritySignal,
    Signals,
    TrafficSignal,
    DataQualitySignal,
    ValidationResult,
    ValidationStatus,
)
from jevcity.simulation.resource_pool import ResourcePool

from ..laya_adapter.adapter import (
    answer_confidence_priority,
    priority_distribution,
    recommended_resource_type,
    suggested_needs_human_review,
    suggested_priority,
)
from ..lineage import build_lineage
from ..policy_position import UNDERSERVED_ZONES, equity_step_up, weights_for
from .allocate import allocate_for_incident
from .confidence import (
    LAYA_ANSWER_CONFIDENCE_GATE,
    OVERALL_GATE,
    critical_signal_count,
    overall_confidence,
)

R_INPUT_REJECT = "R-INPUT-REJECT-01"
R_MODEL_FAILURE = "R-MODEL-FAILURE-HOLD-01"
R_DQ_HOLD = "R-DATA-QUALITY-HOLD-01"
R_LOW_CONF = "R-LOW-CONFIDENCE-HOLD-01"
R_INV5 = "R-INV-5-CRITICAL-NEEDS-TWO-SIGNALS-01"
R_LAYA_CRITICAL_BLOCKED = "R-LAYA-CRITICAL-BLOCKED-INSUFFICIENT-SIGNALS-01"
R_LAYA_LOW_AC = "R-LAYA-LOW-ANSWER-CONFIDENCE-01"
R_LAYA_REVIEW = "R-LAYA-HUMAN-REVIEW-SUGGESTED-01"
R_LAYA_FALLBACK = "R-LAYA-FALLBACK-POLICY-ONLY-01"
R_LAYA_DEGRADED = "R-LAYA-MODEL-DEGRADED-01"
R_CONTENTION = "R-CONTENTION-ESCALATE-01"
R_AUTO = "R-AUTO-APPROVE-01"
R_EQUITY = "R-EQUITY-UNSERVED-01"
R_ECO = "R-ECO-ELECTRIC-FIRST-01"

CRITICAL_TRAFFIC_THRESHOLD = 0.6


@dataclass
class DecisionContext:
    incident: IncidentRecord
    validation: ValidationResult
    severity: ModelOutput
    traffic: ModelOutput
    anomaly: AnomalyOutput
    contradictions: list[str]
    laya: NormalizedLayaResponse
    pool: ResourcePool
    now: datetime
    active_competing_incidents: int = 0
    laya_mode: LayaMode = LayaMode.MOCK
    decision_id: str = "dec-000000"
    policy_position: PolicyPosition = PolicyPosition.RESPONSE_TIME


def decide(ctx: DecisionContext) -> DecisionRecord:
    rules: list[str] = []
    reasons: list[str] = []

    signals = _signals(ctx)
    laya_ok = ctx.laya.status == LayaStatus.OK
    sug_priority = suggested_priority(ctx.laya) if laya_ok else None
    sug_review = suggested_needs_human_review(ctx.laya) if laya_ok else None
    ac_priority = answer_confidence_priority(ctx.laya) if laya_ok else None
    rec_resource = recommended_resource_type(ctx.laya) if laya_ok else None

    base = _record(ctx, signals, rules, reasons, state=DecisionState.HOLD_FOR_HUMAN,
                   priority=Priority.LOW, laya=ctx.laya, laya_ok=laya_ok,
                   sug_priority=sug_priority, sug_review=sug_review,
                   rec_resource=rec_resource, ac_priority=ac_priority)

    overall = overall_confidence(
        ctx.severity.confidence, ctx.traffic.confidence, ctx.anomaly.data_quality_score
    )

    # --- Invariant 1: hard invalid input ------------------------------
    if ctx.validation.validation_status == ValidationStatus.HARD_REJECTED:
        rules.append(R_INPUT_REJECT)
        reasons.append("Hard-invalid input rejected; automated priority suppressed.")
        return _finalize(base, ctx, DecisionState.REJECTED_INPUT, Priority.LOW,
                         DecisionSource.HUMAN_REQUIRED, rules=rules, reasons=reasons,
                         allocation=None, overall=overall)

    # --- Invariant 4: model failure cannot auto-decide ----------------
    failed = [
        m.model_name
        for m in (ctx.severity, ctx.traffic)
        if m.status != ModelStatus.OK
    ]
    anomaly_failed = "anomaly_model_failure" in ctx.anomaly.reasons
    if failed or anomaly_failed:
        rules.append(R_MODEL_FAILURE)
        names = ", ".join(failed) if failed else "anomaly_detector"
        reasons.append(f"Model failure ({names}); routed to human review (MODEL_DEGRADED).")
        state_priority = _priority_or_low(ctx.severity)
        return _finalize(base, ctx, DecisionState.MODEL_DEGRADED, state_priority,
                         DecisionSource.HUMAN_REQUIRED, rules=rules, reasons=reasons,
                         allocation=None, overall=overall)

    # --- signal combination (models only — never Laya) ----------------
    sev_pred = Priority(ctx.severity.prediction) if ctx.severity.prediction else Priority.LOW
    traffic_delta = float(ctx.traffic.prediction or 0.0)
    count = critical_signal_count(
        severity_crossed=sev_pred == Priority.CRITICAL,
        traffic_crossed=traffic_delta >= CRITICAL_TRAFFIC_THRESHOLD,
        situational_anomaly=ctx.anomaly.situational_anomaly,
    )

    priority = sev_pred
    if sev_pred == Priority.CRITICAL and count < 2:
        priority = Priority.HIGH
        rules.append(R_INV5)
        reasons.append(
            "Policy invariant 5 requires two independent supporting model signals for CRITICAL."
        )

    # --- Laya advisory handling (Invariants 9, 10, 12) ----------------
    hold_rules: list[tuple[str, str]] = []
    if not laya_ok:
        rules.append(R_LAYA_FALLBACK)
        reasons.append(f"Laya unavailable ({ctx.laya.status.value}); policy-only fallback.")
    else:
        assert sug_priority is not None
        if sug_priority == Priority.CRITICAL and priority != Priority.CRITICAL:
            rules.append(R_LAYA_CRITICAL_BLOCKED)
            reasons.append(
                "Laya suggested CRITICAL, but fewer than two independent upstream model "
                "signals crossed their CRITICAL threshold."
            )
        if sug_review:
            hold_rules.append((
                R_LAYA_REVIEW,
                "Laya recommended human review for this incident.",
            ))
        if ac_priority is None or ac_priority < LAYA_ANSWER_CONFIDENCE_GATE:
            hold_rules.append((
                R_LAYA_LOW_AC,
                "Laya priority answer_confidence below gate (uncalibrated; Invariant 11).",
            ))

    # --- data quality (Invariant 2) -----------------------------------
    if ctx.anomaly.data_quality_anomaly:
        if priority == Priority.CRITICAL:
            priority = Priority.HIGH
            rules.append(R_INV5)
        hold_rules.append((
            R_DQ_HOLD,
            "Data-quality anomaly detected: " + ", ".join(ctx.anomaly.reasons) + ".",
        ))

    # --- equity position (enhancement 2): underserved-zone step-up -----
    if (
        ctx.policy_position == PolicyPosition.EQUITY
        and ctx.incident.zone in UNDERSERVED_ZONES
    ):
        raised = equity_step_up(priority)
        if raised != priority:
            priority = raised
            rules.append(R_EQUITY)
            reasons.append(
                "Equity policy: priority raised one step for underserved zone "
                f"{ctx.incident.zone.value}."
            )

    # --- confidence gates (§5.8) --------------------------------------
    if overall < OVERALL_GATE:
        hold_rules.append((
            R_LOW_CONF,
            f"Overall confidence {overall:.2f} below gate {OVERALL_GATE:.2f}; "
            "case routed to human review.",
        ))

    if hold_rules:
        for rule, reason in hold_rules:
            rules.append(rule)
            reasons.append(reason)
        reasons.append("Case routed to human review.")
        return _finalize(base, ctx, DecisionState.HOLD_FOR_HUMAN, priority,
                         DecisionSource.HUMAN_REQUIRED, rules=rules, reasons=reasons,
                         allocation=None, overall=overall)

    # --- degraded Laya but policy still operating ---------------------
    if not laya_ok:
        rules.append(R_LAYA_DEGRADED)
        state = DecisionState.MODEL_DEGRADED
        source = DecisionSource.FALLBACK_RULE
    else:
        state = DecisionState.AUTO_APPROVED
        rules.append(R_AUTO)
        source = (
            DecisionSource.LAYA_PROPOSED
            if sug_priority == priority
            else DecisionSource.POLICY_FINALIZED
        )

    # --- allocation ----------------------------------------------------
    recommended = [rec_resource] if rec_resource else []
    allocation = allocate_for_incident(
        ctx.pool,
        incident_id=ctx.incident.incident_id,
        zone=ctx.incident.zone,
        incident_type=ctx.incident.incident_type,
        priority=priority,
        recommended=recommended,
        policy_position=ctx.policy_position,
    )
    if ctx.policy_position == PolicyPosition.ECO:
        rules.append(R_ECO)
        reasons.append(
            "Eco policy: allocation picks the candidate with the highest eco_score."
        )
    if allocation.contention:
        rules.append(R_CONTENTION)
        reasons.append(
            "Required resources unavailable; contention escalation instead of a "
            "false successful allocation."
        )
        return _finalize(base, ctx, DecisionState.CONTENTION_ESCALATION, priority,
                         source, rules=rules, reasons=reasons, allocation=allocation,
                         overall=overall)

    reasons.append(f"Automated decision approved at {priority.value} priority.")
    return _finalize(base, ctx, state, priority, source, rules=rules, reasons=reasons,
                     allocation=allocation, overall=overall)


# --- helpers ----------------------------------------------------------


def _signals(ctx: DecisionContext) -> Signals:
    return Signals(
        severity=SeveritySignal(
            status=ctx.severity.status,
            prediction=ctx.severity.prediction,
            confidence=ctx.severity.confidence,
        ),
        traffic=TrafficSignal(
            status=ctx.traffic.status,
            predicted_congestion_delta=(
                float(ctx.traffic.prediction) if ctx.traffic.prediction else None
            ),
            confidence=ctx.traffic.confidence,
        ),
        data_quality=DataQualitySignal(
            data_quality_score=ctx.anomaly.data_quality_score,
            anomaly=ctx.anomaly.data_quality_anomaly,
            reasons=ctx.anomaly.reasons,
        ),
        situational_anomaly=ctx.anomaly.situational_anomaly,
        anomaly=ctx.anomaly,
    )


def _priority_or_low(severity: ModelOutput) -> Priority:
    if severity.status == ModelStatus.OK and severity.prediction:
        p = Priority(severity.prediction)
        return p if p != Priority.CRITICAL else Priority.HIGH
    return Priority.LOW


def _record(
    ctx: DecisionContext,
    signals: Signals,
    rules: list[str],
    reasons: list[str],
    *,
    state: DecisionState,
    priority: Priority,
    laya,
    laya_ok: bool,
    sug_priority,
    sug_review,
    rec_resource,
    ac_priority,
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=ctx.decision_id,
        incident_id=ctx.incident.incident_id,
        state=state,
        priority=priority,
        matched_rules=list(rules),
        signals=signals,
        laya=_laya_block(ctx, laya, laya_ok, sug_priority, sug_review, rec_resource, ac_priority),
        laya_answer_confidence=ac_priority,
        recommended_resources=[rec_resource] if rec_resource else [],
        reasons=list(reasons),
        decision_time_simulated=ctx.now,
        policy_position=ctx.policy_position,
        objective_weights=weights_for(ctx.policy_position),
    )


def _laya_block(ctx, laya, laya_ok, sug_priority, sug_review, rec_resource, ac_priority):
    from jevcity.schemas import LayaBlock

    return LayaBlock(
        status=laya.status,
        checkpoint=laya.checkpoint,
        router_model=laya.router_model,
        device=laya.device,
        suggested_priority=sug_priority,
        suggested_needs_human_review=sug_review,
        recommended_resource_type=rec_resource,
        answer_confidence_priority=ac_priority,
        distribution=priority_distribution(laya),
        state_hash=laya.state_hash,
        questions_hash=laya.questions_hash,
        latency_ms=laya.latency_ms,
        guardrail_applied=True,
        final_decision_source=DecisionSource.POLICY_FINALIZED,
    )


def _finalize(
    base: DecisionRecord,
    ctx: DecisionContext,
    state: DecisionState,
    priority: Priority,
    source: DecisionSource,
    *,
    rules: list[str],
    reasons: list[str],
    allocation,
    overall: float | None = None,
) -> DecisionRecord:
    update: dict = {
        "state": state,
        "priority": priority,
        "matched_rules": list(dict.fromkeys(rules)),
        "reasons": list(dict.fromkeys(reasons)),
        "overall_confidence": overall if overall is not None else base.overall_confidence,
        "lineage": build_lineage(
            base.signals,
            rules,
            laya=base.laya,
            final_priority=priority,
            assigned_resource_ids=allocation.assigned_ids if allocation is not None else None,
            contention=allocation.contention if allocation is not None else False,
        ),
    }
    if base.laya is not None:
        update["laya"] = base.laya.model_copy(update={"final_decision_source": source})
    if allocation is not None:
        update["assigned_resource_ids"] = allocation.assigned_ids
        update["available_resource_ids"] = allocation.available_ids
        if allocation.requested_types:
            update["recommended_resources"] = allocation.requested_types
    return base.model_copy(update=update)
