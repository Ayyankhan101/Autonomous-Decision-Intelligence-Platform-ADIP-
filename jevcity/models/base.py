"""Stable internal model API (plan Phase 2): decision engine calls this, never raw model code."""
from __future__ import annotations

from typing import Protocol

from jevcity.schemas import AnomalyOutput, EventEnvelope, ModelOutput, ValidationResult


class PredictionModel(Protocol):
    name: str
    version: str

    def predict(self, features: dict) -> ModelOutput: ...


class AnomalyModel(Protocol):
    name: str
    version: str

    def predict(
        self,
        features: dict,
        reports: list[EventEnvelope],
        validation: ValidationResult,
        contradictions: list[str],
    ) -> AnomalyOutput: ...
