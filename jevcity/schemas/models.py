"""Model output contracts (plan §3.1). Every ML agent conforms."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import ModelStatus


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ModelStatus
    model_name: str
    model_version: str
    prediction: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    error_code: str | None = None
    latency_ms: float = Field(ge=0)
    explanation_factors: list[str] = Field(default_factory=list)

    @classmethod
    def failed(
        cls,
        model_name: str,
        model_version: str,
        status: ModelStatus,
        error_code: str,
        latency_ms: float = 0.0,
    ) -> ModelOutput:
        return cls(
            status=status,
            model_name=model_name,
            model_version=model_version,
            prediction=None,
            confidence=None,
            error_code=error_code,
            latency_ms=latency_ms,
        )


class AnomalyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_quality_anomaly: bool
    data_quality_score: float = Field(ge=0, le=1, description="badness: higher = more anomalous")
    situational_anomaly: bool
    reasons: list[str] = Field(default_factory=list)
