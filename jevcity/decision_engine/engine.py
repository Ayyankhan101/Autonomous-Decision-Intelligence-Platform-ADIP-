"""Decision engine orchestrator: validation → correlation → features → model outputs →
Laya advisory → guardrail → audit. Live path persists; What-If path never does (Invariants 6/15)."""
from __future__ import annotations

import copy

from jevcity.audit.log import AuditLog
from jevcity.features.engineer import build_features, history_features
from jevcity.ingestion.correlate import correlate
from jevcity.ingestion.validate import validate_raw
from jevcity.models.anomaly import AnomalyDetector
from jevcity.models.severity import SeverityModel
from jevcity.models.traffic import TrafficModel
from jevcity.models.wrapper import AnomalyWrapper, ModelWrapper
from jevcity.schemas import (
    AuditLayaMetadata,
    DecisionRecord,
    DecisionState,
    EventEnvelope,
    IncidentLifecycle,
    IncidentType,
    LayaMode,
    ModelStatus,
    NormalizedLayaResponse,
    OverrideRecord,
    OverrideRequest,
    Priority,
    ResourceType,
    ValidationResult,
    ValidationStatus,
    Zone,
    WhatIfRequest,
    WhatIfResult,
    WhatIfScenario,
)
from jevcity.simulation.state import SimulationState
from jevcity.schemas.resources import IncidentRecord

from .guardrail.policy import DecisionContext, decide
from .laya_adapter.adapter import LayaAdapter
from .laya_adapter.state_builder import build_state


class JevCityEngine:
    def __init__(
        self,
        simulation: SimulationState,
        *,
        adapter: LayaAdapter | None = None,
        audit: AuditLog | None = None,
        severity: SeverityModel | None = None,
        traffic: TrafficModel | None = None,
        anomaly: AnomalyDetector | None = None,
    ) -> None:
        self.simulation = simulation
        self.adapter = adapter or LayaAdapter(mode=LayaMode.MOCK)
        self.audit = audit or AuditLog()
        self.severity = ModelWrapper(severity or SeverityModel())
        self.traffic = ModelWrapper(traffic or TrafficModel())
        self.anomaly = AnomalyWrapper(anomaly or AnomalyDetector())
        self.decisions: dict[str, DecisionRecord] = {}
        self.decision_history: list[DecisionRecord] = []
        self.validation_by_event: dict[str, ValidationResult] = {}
        self._processed = 0
        self._counter = 0

    # --- live path ------------------------------------------------------

    def process_pending(self) -> list[DecisionRecord]:
        """One decision per incident per batch: every raw event is validated, but
        correlated reports re-evaluate the same incident once (latest state wins)."""
        pending = self.simulation.raw_events[self._processed:]
        self._processed = len(self.simulation.raw_events)
        for raw in pending:
            validation = validate_raw(raw)
            self.validation_by_event[validation.event_id] = validation
        by_incident: dict[str, dict] = {}
        for raw in pending:
            by_incident[str(raw.get("incident_id", "unknown"))] = raw
        return [self._process_one(raw) for raw in by_incident.values()]

    def _process_one(self, raw: dict) -> DecisionRecord:
        validation = validate_raw(raw)
        incident_id = str(raw.get("incident_id", "unknown"))
        incident = self.simulation.incidents.get(incident_id)
        if incident is None:
            incident = self._rejected_shell(incident_id, validation)
            self.simulation.incidents[incident_id] = incident

        if validation.validation_status == ValidationStatus.HARD_REJECTED:
            incident.validation_status = ValidationStatus.HARD_REJECTED
            record = self._rejected_decision(incident, validation)
            self._persist(record, incident, validation)
            return record

        record = self.decide_for(
            incident_id,
            pool=self.simulation.pool,
            adapter=self.adapter,
            dry_run=False,
        )
        self._persist(record, incident, validation)
        return record

    def _rejected_decision(
        self, incident: IncidentRecord, validation: ValidationResult
    ) -> DecisionRecord:
        """Invariant 1: hard-invalid input never reaches models or Laya."""
        from jevcity.schemas import DataQualitySignal, SeveritySignal, Signals, TrafficSignal

        self._counter += 1
        return DecisionRecord(
            decision_id=f"dec-{self._counter:06d}",
            incident_id=incident.incident_id,
            state=DecisionState.REJECTED_INPUT,
            priority=Priority.LOW,
            matched_rules=["R-INPUT-REJECT-01"],
            signals=Signals(
                severity=SeveritySignal(status=ModelStatus.INVALID_INPUT),
                traffic=TrafficSignal(status=ModelStatus.INVALID_INPUT),
                data_quality=DataQualitySignal(
                    data_quality_score=1.0, anomaly=True,
                    reasons=["hard_invalid_input"],
                ),
            ),
            laya=None,
            reasons=[
                "Hard-invalid input rejected; automated priority suppressed.",
                "; ".join(f.message for f in validation.hard_errors[:5]),
            ],
            decision_time_simulated=self.simulation.clock.now,
        )

    def decide_for(
        self,
        incident_id: str,
        *,
        pool,
        adapter: LayaAdapter,
        dry_run: bool = False,
    ) -> DecisionRecord:
        """Pure decision computation against `pool` (live or sandbox). No persistence."""
        incident = self.simulation.incidents[incident_id]
        reports = self.simulation.reports_for(incident_id)
        validation = self._validation_for(incident_id, reports)

        if not reports:
            raise KeyError(f"no reports for incident {incident_id}")

        correlation = correlate(reports)
        primary = sorted(reports, key=lambda e: e.simulated_time)[0]
        features = build_features(
            reports,
            history=history_features(
                self.simulation.incidents,
                primary.location.zone.value,
                primary.incident_type.value,
                exclude_id=incident_id,
            ),
        )
        severity_out = self.severity.predict(features)
        traffic_out = self.traffic.predict(features)
        anomaly_out = self.anomaly.predict(
            features, reports, validation, correlation.contradictions
        )

        competing = sum(
            1
            for inc in self.simulation.incidents.values()
            if inc.incident_id != incident_id
            and inc.lifecycle
            in (
                IncidentLifecycle.DETECTED,
                IncidentLifecycle.VALIDATED,
                IncidentLifecycle.PRIORITIZED,
                IncidentLifecycle.RESOURCE_ASSIGNED,
                IncidentLifecycle.ACTIVE,
            )
        )
        state = build_state(
            incident_id=incident_id,
            primary=primary,
            features=features,
            severity=severity_out,
            traffic=traffic_out,
            anomaly=anomaly_out,
            available_ambulances=pool.available_count(ResourceType.AMBULANCE),
            active_competing_incidents=competing,
        )
        laya_response: NormalizedLayaResponse = adapter.ask(state)

        self._counter += 1
        record = decide(
            DecisionContext(
                incident=incident,
                validation=validation,
                severity=severity_out,
                traffic=traffic_out,
                anomaly=anomaly_out,
                contradictions=correlation.contradictions,
                laya=laya_response,
                pool=pool,
                now=self.simulation.clock.now,
                active_competing_incidents=competing,
                laya_mode=adapter.mode,
                decision_id=f"dec-{self._counter:06d}",
            )
        )
        return record.model_copy(update={"dry_run": dry_run})

    # --- persistence ----------------------------------------------------

    def _persist(
        self,
        record: DecisionRecord,
        incident: IncidentRecord,
        validation: ValidationResult,
    ) -> DecisionRecord:
        self.decisions[record.decision_id] = record
        self.decision_history.append(record)
        self._advance_lifecycle(incident, record)
        self._append_audit(record, incident, validation)
        return record

    @staticmethod
    def _advance_lifecycle(incident: IncidentRecord, record: DecisionRecord) -> None:
        if record.state == DecisionState.REJECTED_INPUT:
            incident.validation_status = ValidationStatus.HARD_REJECTED
            return
        if record.assigned_resource_ids:
            incident.assigned_resource_ids = list(record.assigned_resource_ids)
            incident.lifecycle = IncidentLifecycle.RESOURCE_ASSIGNED
        elif record.state in (DecisionState.AUTO_APPROVED, DecisionState.MODEL_DEGRADED):
            incident.lifecycle = IncidentLifecycle.PRIORITIZED
        elif incident.lifecycle == IncidentLifecycle.DETECTED:
            incident.lifecycle = IncidentLifecycle.VALIDATED

    def _append_audit(
        self,
        record: DecisionRecord,
        incident: IncidentRecord,
        validation: ValidationResult,
    ) -> None:
        laya = record.laya
        self.audit.append(
            actor="system",
            action="DECISION_EMITTED",
            reason="; ".join(record.reasons)[:1900],
            before_state=incident.lifecycle.value,
            after_state=record.state.value,
            decision_id=record.decision_id,
            incident_id=record.incident_id,
            policy_version=record.policy_version,
            model_versions={
                "severity": self.severity.version,
                "traffic": self.traffic.version,
                "anomaly": self.anomaly.version,
                "laya_checkpoint": laya.checkpoint if laya else "none",
            },
            laya=AuditLayaMetadata(
                laya_checkpoint=laya.checkpoint if laya else None,
                laya_router_model=laya.router_model if laya else None,
                laya_status=laya.status if laya else None,
                laya_state_hash=laya.state_hash if laya else None,
                laya_questions_hash=laya.questions_hash if laya else None,
                laya_suggested_priority=laya.suggested_priority if laya else None,
                laya_answer_confidence_priority=(
                    laya.answer_confidence_priority if laya else None
                ),
                laya_latency_ms=laya.latency_ms if laya else None,
                laya_guardrail_applied=laya.guardrail_applied if laya else None,
            ),
            timestamp=self.simulation.clock.now,
        )

    # --- overrides (Invariant 7) ----------------------------------------

    def apply_override(self, req: OverrideRequest) -> DecisionRecord:
        original = self.decisions.get(req.decision_id)
        if original is None:
            raise KeyError(f"unknown decision {req.decision_id}")
        new_priority = req.new_priority or original.priority
        self._counter += 1
        override_record = original.model_copy(
            update={
                "decision_id": f"dec-{self._counter:06d}",
                "state": DecisionState.OVERRIDE_ACTIVE,
                "priority": new_priority,
                "matched_rules": original.matched_rules + ["R-OVERRIDE-01"],
                "reasons": original.reasons
                + [f"Operator {req.operator_id} overrode decision "
                   f"({req.override_type.value}): {req.reason}"],
                "override": OverrideRecord(
                    operator_id=req.operator_id,
                    override_type=req.override_type,
                    reason=req.reason,
                    timestamp=self.simulation.clock.now,
                    previous_state=original.state,
                    previous_priority=original.priority,
                ),
                "assigned_resource_ids": (
                    list(original.assigned_resource_ids)
                    if req.override_type.value != "ASSIGN_RESOURCES"
                    else self._assign_recommended(original)
                ),
            }
        )
        self.decisions[override_record.decision_id] = override_record
        self.decision_history.append(override_record)
        incident = self.simulation.incidents[original.incident_id]
        self.audit.append(
            actor=req.operator_id,
            action="OVERRIDE_APPLIED",
            reason=req.reason,
            before_state=original.state.value,
            after_state=DecisionState.OVERRIDE_ACTIVE.value,
            decision_id=original.decision_id,
            incident_id=original.incident_id,
            policy_version=original.policy_version,
            timestamp=self.simulation.clock.now,
        )
        if override_record.assigned_resource_ids != original.assigned_resource_ids:
            incident.assigned_resource_ids = list(
                override_record.assigned_resource_ids
            )
        return override_record

    def _assign_recommended(self, record: DecisionRecord) -> list[str]:
        assigned = list(record.assigned_resource_ids)
        for rtype in record.recommended_resources:
            candidates = self.simulation.pool.available(rtype)
            if candidates:
                pick = sorted(candidates, key=lambda r: r.resource_id)[0]
                self.simulation.pool.assign(pick.resource_id, record.incident_id)
                assigned.append(pick.resource_id)
        return assigned

    # --- What-If (Invariants 6, 15) -------------------------------------

    def run_what_if(self, req: WhatIfRequest) -> WhatIfResult:
        sandbox_pool = copy.deepcopy(self.simulation.pool)
        incidents = list(self.simulation.incidents.values())
        decidable = [i for i in incidents if self.simulation.reports_for(i.incident_id)]
        if not decidable:
            raise RuntimeError("no decidable incidents to run What-If against")
        target = decidable[-1]
        if req.scenario == WhatIfScenario.REMOVE_ONE_AMBULANCE:
            removable = [
                r for r in sandbox_pool.all()
                if r.type == ResourceType.AMBULANCE
            ]
            if removable:
                sandbox_pool.remove(sorted(removable, key=lambda r: r.resource_id)[0].resource_id)
        elif req.scenario == WhatIfScenario.CLOSE_ROAD:
            pass  # same target; feature-level scenario hooks come in Phase 5
        elif req.scenario == WhatIfScenario.SECOND_EMERGENCY:
            self.simulation.second_emergency()
            pending = self.simulation.raw_events[self._processed:]
            if pending:
                shell_id = str(pending[-1].get("incident_id"))
                shell = self.simulation.incidents.get(shell_id)
                if shell is None:
                    shell = self._rejected_shell(shell_id, validate_raw(pending[-1]))
                    self.simulation.incidents[shell_id] = shell
                target = shell

        sandbox_adapter = LayaAdapter(mode=LayaMode.MOCK, cache={})
        record = self.decide_for(
            target.incident_id,
            pool=sandbox_pool,
            adapter=sandbox_adapter,
            dry_run=True,
        )

        if req.scenario == WhatIfScenario.SECOND_EMERGENCY:
            # roll the sandbox-only incident back out of the live registry
            self.simulation.incidents.pop(target.incident_id, None)
            self.simulation.raw_events = self.simulation.raw_events[: self._processed]
            self.simulation.events = [
                e for e in self.simulation.events if e.incident_id != target.incident_id
            ]

        return WhatIfResult(
            sandbox_id=f"sbx-{self._counter + 1:06d}",
            scenario=req.scenario,
            dry_run=True,
            laya_mode=sandbox_adapter.mode.value,
            decision=record,
            audit_written=False,
            live_state_mutated=False,
        )

    # --- helpers ---------------------------------------------------------

    def _validation_for(
        self, incident_id: str, reports: list[EventEnvelope]
    ) -> ValidationResult:
        found = [
            v for v in self.validation_by_event.values() if v.incident_id == incident_id
        ]
        if found:
            for status in (
                ValidationStatus.HARD_REJECTED,
                ValidationStatus.SOFT_FLAGGED,
                ValidationStatus.VALID,
            ):
                for v in found:
                    if v.validation_status == status:
                        return v
        if not reports:
            raise ValueError("no reports")
        return validate_raw(reports[0].model_dump(mode="json"))

    @staticmethod
    def _rejected_shell(incident_id: str, validation: ValidationResult) -> IncidentRecord:
        from datetime import UTC, datetime

        return IncidentRecord(
            incident_id=incident_id,
            incident_type=IncidentType.ACCIDENT,
            zone=Zone.NORTH,
            lifecycle=IncidentLifecycle.DETECTED,
            validation_status=ValidationStatus.HARD_REJECTED,
            first_seen_simulated=datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
            latest_simulated=datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
            report_count=1,
        )
