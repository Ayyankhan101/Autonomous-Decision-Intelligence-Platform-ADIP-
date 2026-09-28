"""Input-validation result (plan: validation point 1 — before feature engineering)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import ValidationStatus


class ValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: str = Field(pattern="^(hard|soft)$")
    code: str
    message: str


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    incident_id: str
    validation_status: ValidationStatus
    hard_errors: list[ValidationFinding] = Field(default_factory=list)
    soft_warnings: list[ValidationFinding] = Field(default_factory=list)
    data_quality_score: float = Field(default=0.0, ge=0, le=1)
