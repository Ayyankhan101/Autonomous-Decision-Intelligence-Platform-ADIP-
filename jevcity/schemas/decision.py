"""Extended decision record (plan §3.1.3). state vs priority are separate fields.

Key Rule (plan): priority = final governed priority; laya.suggested_priority = model
suggestion. Never silently overwrite one with the other.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    DecisionSource,
    DecisionState,
    ImpactTier,
    LayaStatus,
    ModelStatus,
    OverrideContextCode,
    OverrideReasonCode,
    OverrideType,
    PolicyPosition,
    Priority,
    ResourceType,
)
from .models import AnomalyOutput

POLICY_ID = "city-priority-policy"
POLICY_VERSION = "0.1.0"


class SeveritySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ModelStatus = ModelStatus.OK
    prediction: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class TrafficSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ModelStatus = ModelStatus.OK
    predicted_congestion_delta: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class DataQualitySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_quality_score: float = Field(ge=0, le=1)
    anomaly: bool = False
    reasons: list[str] = Field(default_factory=list)


class Signals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: SeveritySignal
    traffic: TrafficSignal
    data_quality: DataQualitySignal
    situational_anomaly: bool = False
    anomaly: AnomalyOutput | None = None


class LineageTerm(BaseModel):
    """One normalised evidence contribution (enhancement 3: all terms on a common 0-1 scale)."""

    model_config = ConfigDict(extra="forbid")

    label: str
    score: float = Field(ge=0, le=1)
    direction: Literal["positive", "negative", "neutral"]
    source: str


class LineageBlock(BaseModel):
    """Structured decision lineage: evidence scores -> decisive policy clause (enhancement 3)."""

    model_config = ConfigDict(extra="forbid")

    terms: list[LineageTerm] = Field(min_length=1)
    clause_id: str | None = None
    expression: str = Field(min_length=1)


class LayaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LayaStatus
    checkpoint: str
    router_model: str
    device: str
    suggested_priority: Priority | None = None
    suggested_needs_human_review: bool | None = None
    recommended_resource_type: ResourceType | None = None
    answer_confidence_priority: float | None = Field(default=None, ge=0, le=1)
    distribution: dict[str, float] = Field(default_factory=dict)
    state_hash: str = ""
    questions_hash: str = ""
    latency_ms: float = Field(default=0, ge=0)
    guardrail_applied: bool = True
    final_decision_source: DecisionSource = DecisionSource.POLICY_FINALIZED


class OverrideRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str
    override_type: OverrideType
    reason: str
    timestamp: datetime
    previous_state: DecisionState
    previous_priority: Priority
    cited_clause: str | None = None
    reason_code: OverrideReasonCode | None = None
    impact_tier: ImpactTier | None = None
    context_code: OverrideContextCode | None = None
    break_glass: bool = False


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    incident_id: str
    state: DecisionState
    priority: Priority
    policy_id: str = POLICY_ID
    policy_version: str = POLICY_VERSION
    policy_position: PolicyPosition = PolicyPosition.RESPONSE_TIME
    objective_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Objective weights active when this decision was generated "
        "(response_time / equity / emissions); enhancement 2 audit-trace completeness.",
    )
    matched_rules: list[str] = Field(default_factory=list)
    signals: Signals
    laya: LayaBlock | None = None
    overall_confidence: float | None = Field(default=None, ge=0, le=1)
    laya_answer_confidence: float | None = Field(default=None, ge=0, le=1)
    recommended_resources: list[ResourceType] = Field(default_factory=list)
    assigned_resource_ids: list[str] = Field(default_factory=list)
    available_resource_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    decision_time_simulated: datetime
    dry_run: bool = False
    override: OverrideRecord | None = None
    lineage: LineageBlock | None = None
