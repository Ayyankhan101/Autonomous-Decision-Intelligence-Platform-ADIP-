"""Resource and incident state model (plan §5.7). Frozen contract."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    IncidentLifecycle,
    IncidentType,
    ResourceType,
    ResourceStatus,
    ValidationStatus,
    Zone,
)


class Resource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    type: ResourceType
    zone: Zone
    status: ResourceStatus = ResourceStatus.AVAILABLE
    assigned_incident_id: str | None = None
    eco_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Eco-optimisation fitness (1 = electric/zero-emission response "
        "vehicle, 0 = highest-emission). Used only when the policy position is ECO.",
    )


class IncidentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    incident_type: IncidentType
    zone: Zone
    lifecycle: IncidentLifecycle = IncidentLifecycle.DETECTED
    validation_status: ValidationStatus = ValidationStatus.VALID
    first_seen_simulated: datetime
    latest_simulated: datetime
    source_ids: list[str] = Field(default_factory=list)
    report_count: int = Field(default=0, ge=0)
    assigned_resource_ids: list[str] = Field(default_factory=list)
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Free-text notes carried from the originating report "
        "(display-only; never enters the Laya state, Invariant 16).",
    )
