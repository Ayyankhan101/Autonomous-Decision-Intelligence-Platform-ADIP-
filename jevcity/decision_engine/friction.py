"""Zero-trust override friction (enhancement 4): rule-based impact estimator + tier gating.

Classifies every proposed human override before it is applied:
- LOW: no urgency/allocation change projected — acknowledge and go.
- HIGH: priority raise, or dismissing an incident that holds units — structured
  context code + explicit acknowledgment required (constructive friction).
- BREAK_GLASS: priority raise on a life-safety incident (fire/accident) — friction
  never blocks the action, but break_glass=true is required and the audit entry is
  flagged for immediate post-event review.

Estimator is deterministic and rule-based (no trained model), per the addendum:
"using the existing incident-simulation module or a lightweight rule-based impact
estimator rather than an additional trained model".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from jevcity.schemas import (
    DecisionRecord,
    ImpactTier,
    IncidentRecord,
    IncidentType,
    OverrideType,
    Priority,
)

_PRIORITY_RANK = {Priority.CRITICAL: 3, Priority.HIGH: 2, Priority.MEDIUM: 1, Priority.LOW: 0}

LIFE_SAFETY_TYPES = frozenset({IncidentType.FIRE, IncidentType.ACCIDENT})


@dataclass
class FrictionAssessment:
    tier: ImpactTier
    warning: str
    projected: dict[str, str | int | bool] = field(default_factory=dict)

    @property
    def requires_ack(self) -> bool:
        return self.tier != ImpactTier.LOW

    @property
    def requires_context_code(self) -> bool:
        return self.tier == ImpactTier.HIGH

    @property
    def requires_break_glass(self) -> bool:
        return self.tier == ImpactTier.BREAK_GLASS


def _is_priority_raise(decision: DecisionRecord, new_priority: Priority | None) -> bool:
    if new_priority is None:
        return False
    return _PRIORITY_RANK[new_priority] > _PRIORITY_RANK[decision.priority]


def assess(
    decision: DecisionRecord,
    override_type: OverrideType,
    new_priority: Priority | None,
    incident: IncidentRecord,
    *,
    available_recommended: int,
) -> FrictionAssessment:
    raise_priority = _is_priority_raise(decision, new_priority)
    life_safety = incident.incident_type in LIFE_SAFETY_TYPES
    dismiss_with_units = (
        override_type == OverrideType.DISMISS_INCIDENT
        and bool(decision.assigned_resource_ids)
    )
    zone = incident.zone.value
    types = ",".join(t.value for t in decision.recommended_resources) or "any"
    projected: dict[str, str | int | bool] = {
        "zone": zone,
        "priority_from": decision.priority.value,
        "priority_to": (new_priority or decision.priority).value,
        "life_safety": life_safety,
        "units_assigned": len(decision.assigned_resource_ids),
        "recommended_types": types,
        "available_recommended": available_recommended,
    }

    if life_safety and raise_priority:
        warning = (
            f"BREAK-GLASS LIFE-SAFETY: priority {decision.priority.value} -> "
            f"{new_priority.value} on life-safety incident "
            f"{incident.incident_type.value} in zone {zone}; estimated impact: "
            f"{available_recommended} recommended unit(s) available ({types}). "
            "Break-glass override remains available and is automatically flagged "
            "for immediate post-event review."
        )
        return FrictionAssessment(ImpactTier.BREAK_GLASS, warning, projected)

    if raise_priority:
        warning = (
            f"HIGH RISK: priority {decision.priority.value} -> {new_priority.value} "
            f"raises dispatch urgency in zone {zone}; estimated impact: "
            f"{available_recommended} recommended unit(s) available ({types}). "
            "Confirm whether external context (e.g. an unmapped physical roadblock) "
            "justifies this override."
        )
        return FrictionAssessment(ImpactTier.HIGH, warning, projected)

    if dismiss_with_units:
        warning = (
            f"HIGH RISK: dismissing this incident releases "
            f"{len(decision.assigned_resource_ids)} assigned unit(s) in zone {zone}; "
            "downstream coverage decreases. Confirm whether external context "
            "justifies this override."
        )
        return FrictionAssessment(ImpactTier.HIGH, warning, projected)

    return FrictionAssessment(
        ImpactTier.LOW,
        "LOW RISK: no urgency or allocation change projected; operator acknowledgment "
        "suffices.",
        projected,
    )


def enforce(assessment: FrictionAssessment, req) -> None:
    """Raise ValueError (mapped to 422) when tier requirements are unmet."""
    if assessment.tier == ImpactTier.HIGH:
        if not req.impact_ack or req.context_code is None:
            raise ValueError(
                "HIGH-risk override requires impact_ack=true and a context_code"
            )
    if assessment.tier == ImpactTier.BREAK_GLASS and not req.break_glass:
        raise ValueError("BREAK_GLASS override requires break_glass=true")
