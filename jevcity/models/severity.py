"""Severity/risk prediction — rule-table baseline (plan Phase 2 allows strong baseline;
this is the documented MVP proxy, replaced by gradient boosting later)."""
from __future__ import annotations

from jevcity.schemas import ModelOutput, ModelStatus, Priority


class SeverityModel:
    name = "severity_predictor"
    version = "sev-rule-0.1.0"

    def __init__(self, fail: ModelStatus | None = None) -> None:
        self.fail = fail

    def predict(self, features: dict) -> ModelOutput:
        if self.fail is not None:
            return ModelOutput.failed(
                self.name, self.version, self.fail, error_code="MODEL_FAILURE"
            )

        factors: list[str] = []
        injuries = features.get("injuries_reported") or 0
        lanes = features.get("lanes_blocked") or 0
        hint = features.get("severity_hint")
        weather = features.get("weather")
        traffic = features.get("traffic_level")
        vehicles = features.get("vehicles_involved") or 0

        score = 0
        if injuries >= 3:
            score += 3
            factors.append("multiple_injuries")
        elif injuries >= 1:
            score += 2
            factors.append("injuries_reported")
        if lanes >= 2:
            score += 2
            factors.append("lanes_blocked")
        elif lanes == 1:
            score += 1
        if vehicles >= 4:
            score += 2
            factors.append("multiple_vehicles")
        if hint == "severe":
            score += 2
            factors.append("severity_hint_severe")
        elif hint == "moderate":
            score += 1
        if weather in ("rain", "snow"):
            score += 1
            factors.append("adverse_weather")
        if traffic in ("high", "gridlock"):
            score += 1
            factors.append("heavy_traffic")

        if score >= 7:
            prediction, confidence = Priority.CRITICAL, 0.74
        elif score >= 5:
            prediction, confidence = Priority.HIGH, 0.71
        elif score >= 3:
            prediction, confidence = Priority.MEDIUM, 0.66
        else:
            prediction, confidence = Priority.LOW, 0.6
        if not factors:
            factors.append("baseline")
        return ModelOutput(
            status=ModelStatus.OK,
            model_name=self.name,
            model_version=self.version,
            prediction=prediction.value,
            confidence=confidence,
            latency_ms=12.0,
            explanation_factors=factors,
        )
