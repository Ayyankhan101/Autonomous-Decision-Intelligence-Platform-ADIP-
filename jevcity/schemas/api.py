"""API request/response contracts (plan §5 endpoint list + dashboard polling payload)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .audit import AuditEntry
from .decision import DecisionRecord
from .enums import (
    ImpactTier,
    IncidentType,
    InjectionMode,
    LayaMode,
    OverrideContextCode,
    OverrideReasonCode,
    OverrideType,
    PolicyPosition,
    Priority,
    ResourceType,
    SeverityHint,
    WhatIfScenario,
    Zone,
)
from .resources import IncidentRecord, Resource
from .validation import ValidationResult


class StatePayload(BaseModel):
    """GET /api/state — dashboard polls this every 1–2 s."""

    model_config = ConfigDict(extra="forbid")

    simulated_time: datetime
    running: bool
    session_seed: int
    scenario_seed: int
    incident_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    open_incident_count: int = Field(ge=0)
    available_resources: dict[ResourceType, int]
    laya_mode: str
    last_laya_status: str | None = None
    policy_position: PolicyPosition = PolicyPosition.RESPONSE_TIME
    objective_weights: dict[str, float] = Field(default_factory=dict)
    audit_write_failed: bool = Field(
        default=False,
        description="True while the append-only audit log rejects writes; the dashboard "
        "shows a banner because the trail may be incomplete (phase-5 UI state).",
    )


class IncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident: IncidentRecord
    validation: ValidationResult | None = None
    latest_decision: DecisionRecord | None = None


class DecisionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[DecisionRecord]


class IncidentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incidents: list[IncidentRecord]


class ResourceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resources: list[Resource]


class AuditListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[AuditEntry]


class AuditVerifyResponse(BaseModel):
    """GET /api/audit/verify — live hash-chain recompute (demo-liveness pack)."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    entry_count: int = Field(ge=0)
    broken_at: int | None = Field(
        default=None,
        description="1-based position of the first bad entry; None when intact.",
    )


class LayaModeRequest(BaseModel):
    """POST /api/simulation/laya-mode — runtime mock|cache|live adapter switch."""

    model_config = ConfigDict(extra="forbid")

    mode: LayaMode


class LayaModeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_mode: LayaMode
    mode: LayaMode


class SimulationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_seed: int = 42
    scenario_seed: int = 7
    recording: str | None = Field(
        default=None,
        description="JSONL recording filename under datasets/jevcity/ (replay mode)",
    )
    speed: float = Field(default=1.0, gt=0, le=100, description="wall pacing multiplier")


class SimulationResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_seed: int = 42
    scenario_seed: int = 7


class SimulationIncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_type: IncidentType
    zone: Zone
    severity: SeverityHint = SeverityHint.MODERATE
    source_id: str = "sensor-auto-01"
    notes: str | None = Field(default=None, max_length=500)
    multi_report: bool = False


class SimulationBadDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: InjectionMode
    target_incident_id: str | None = None


class SybilFloodRequest(BaseModel):
    """Enhancement 1: Sybil-style flood of fabricated reports from fake identities."""

    model_config = ConfigDict(extra="forbid")

    incident_type: IncidentType = IncidentType.ACCIDENT
    zone: Zone = Zone.EAST
    severity: SeverityHint = SeverityHint.SEVERE
    reports: int = Field(default=5, ge=2, le=10)


class SybilFloodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    incident_id: str
    fake_sources: list[str]
    decision_ids: list[str] = Field(default_factory=list)


class SecondEmergencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_type: IncidentType = IncidentType.FIRE
    zone: Zone = Zone.NORTH


class OverrideRequest(BaseModel):
    """Invariant 7: operator_id and reason are required (min_length=1).

    Enhancement 3 (hyper-explainable audit): when present, cited_clause names the policy
    clause the operator overrode (or a gap marker) and reason_code classifies the
    attribution. Both optional at the API for backward compatibility; the dashboard
    enforces selection before submit.

    Enhancement 4 (zero-trust override friction): the server classifies every override
    into an impact tier (LOW / HIGH / BREAK_GLASS). HIGH-tier overrides require
    impact_ack=true and a context_code; life-safety priority raises are BREAK_GLASS and
    require break_glass=true (flagged for post-event review). LOW-tier overrides need no
    extra fields.
    """

    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    override_type: OverrideType
    reason: str = Field(min_length=1)
    new_priority: Priority | None = None
    cited_clause: str | None = Field(default=None, max_length=120)
    reason_code: OverrideReasonCode | None = None
    impact_ack: bool = False
    context_code: OverrideContextCode | None = None
    break_glass: bool = False


class ImpactPreviewRequest(BaseModel):
    """POST /api/overrides/impact — dry risk preview; never mutates state or audit."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    override_type: OverrideType
    new_priority: Priority | None = None


class ImpactPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    tier: ImpactTier
    warning: str
    requires_ack: bool
    requires_context_code: bool
    requires_break_glass: bool
    projected: dict[str, str | int | bool] = Field(default_factory=dict)


class WhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: WhatIfScenario
    session_seed: int | None = None


class PolicyPositionRequest(BaseModel):
    """POST /api/policy/position — runtime three-position policy selector (E2)."""

    model_config = ConfigDict(extra="forbid")

    position: PolicyPosition
    reoptimise_active: bool = False


class PolicyPositionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_position: PolicyPosition
    position: PolicyPosition
    objective_weights: dict[str, float]
    affected_decisions: list[str] = Field(default_factory=list)
    reoptimised: int = Field(ge=0)


class SimulationActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    incident_id: str | None = None
    decision_ids: list[str] = Field(default_factory=list)


class WhatIfResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sandbox_id: str
    scenario: WhatIfScenario
    dry_run: bool = True
    laya_mode: str
    decision: DecisionRecord
    audit_written: bool = False
    live_state_mutated: bool = False
