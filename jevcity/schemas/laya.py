"""Laya request contract (plan §3.1.1) and normalized response (plan §3.1.2).

answer_confidence: repo alignment — derived in the adapter normalizer (ERRATA C2/C3);
gates use answer_confidence only, never raw `confidence`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import IncidentType, LayaStatus, Zone


class LayaState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    incident_type: IncidentType
    zone: Zone
    simulated_time: datetime
    weather: str | None = None
    traffic_level: str | None = None
    vehicles_involved: int | None = None
    injuries_reported: int | None = None
    lanes_blocked: int | None = None
    severity_prediction: str | None = None
    severity_confidence: float | None = Field(default=None, ge=0, le=1)
    traffic_congestion_delta: float | None = None
    traffic_confidence: float | None = Field(default=None, ge=0, le=1)
    data_quality_score: float = Field(ge=0, le=1)
    data_quality_reasons: list[str] = Field(default_factory=list)
    available_ambulances: int = Field(ge=0)
    active_competing_incidents: int = Field(ge=0)


class QuestionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["choice", "noul"]
    instructions: str
    criteria: dict[str, str]
    labels: dict[str, str] | None = None


class LayaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: LayaState
    questions: dict[str, QuestionDef]


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: str
    confidence: float = Field(ge=0, le=1)
    answer_confidence: float = Field(ge=0, le=1)
    distribution: dict[str, float] = Field(default_factory=dict)


class NoulAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    noul: float = Field(ge=0, le=1)
    answer_confidence: float = Field(ge=0, le=1)


class LayaUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class NormalizedLayaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LayaStatus
    engine: str = "laya"
    runtime: str
    checkpoint: str
    router_model: str
    device: str
    state_hash: str
    questions_hash: str
    answers: dict[str, ChoiceAnswer | NoulAnswer] = Field(default_factory=dict)
    usage: LayaUsage = Field(default_factory=LayaUsage)
    latency_ms: float = Field(default=0, ge=0)
    error_code: str | None = None

    @classmethod
    def failed(
        cls,
        status: LayaStatus,
        *,
        runtime: str,
        checkpoint: str,
        router_model: str,
        device: str,
        state_hash: str,
        questions_hash: str,
        error_code: str,
        latency_ms: float = 0.0,
    ) -> NormalizedLayaResponse:
        return cls(
            status=status,
            runtime=runtime,
            checkpoint=checkpoint,
            router_model=router_model,
            device=device,
            state_hash=state_hash,
            questions_hash=questions_hash,
            error_code=error_code,
            latency_ms=latency_ms,
        )
