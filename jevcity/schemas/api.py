"""API request/response contracts (plan §5 endpoint list + dashboard polling payload)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .audit import AuditEntry
from .decision import DecisionRecord
from .enums import (
    IncidentType,
    InjectionMode,
    OverrideType,
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


class SecondEmergencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_type: IncidentType = IncidentType.FIRE
    zone: Zone = Zone.NORTH


class OverrideRequest(BaseModel):
    """Invariant 7: operator_id and reason are required (min_length=1)."""

    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    override_type: OverrideType
    reason: str = Field(min_length=1)
    new_priority: Priority | None = None


class WhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: WhatIfScenario
    session_seed: int | None = None


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
