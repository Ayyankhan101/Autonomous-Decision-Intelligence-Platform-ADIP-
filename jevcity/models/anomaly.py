"""Anomaly/data-quality detection — split outputs (plan §3.1). Conservative on failure:
if the anomaly model itself fails, treat data as worst-quality (fail closed, Invariant 4/12)."""
from __future__ import annotations

from jevcity.schemas import AnomalyOutput, EventEnvelope, ModelStatus, ValidationResult


class AnomalyDetector:
    name = "anomaly_detector"
    version = "anom-threshold-0.1.0"

    def __init__(self, fail: ModelStatus | None = None) -> None:
        self.fail = fail

    def predict(
        self,
        features: dict,
        reports: list[EventEnvelope],
        validation: ValidationResult,
        contradictions: list[str],
    ) -> AnomalyOutput:
        if self.fail is not None:
            return AnomalyOutput(
                data_quality_anomaly=True,
                data_quality_score=1.0,
                situational_anomaly=False,
                reasons=["anomaly_model_failure"],
            )

        score = 0.05
        reasons: list[str] = []
        if contradictions:
            score += 0.55
            reasons.extend(contradictions)
        if validation.soft_warnings and any(
            w.code == "missing_injury_count" for w in validation.soft_warnings
        ):
            score += 0.25
            reasons.append("missing_injury_count")
        if validation.soft_warnings and any(
            w.code == "injected_data" for w in validation.soft_warnings
        ):
            score += 0.3
            reasons.append("injected_data")
        if validation.validation_status.value == "hard_rejected":
            score = 1.0
            reasons.append("hard_invalid_input")

        vehicles = features.get("vehicles_involved") or 0
        injuries = features.get("injuries_reported") or 0
        situational = vehicles >= 6 or injuries >= 5
        if situational:
            reasons.append("situational_extremes")

        return AnomalyOutput(
            data_quality_anomaly=score >= 0.5,
            data_quality_score=min(1.0, score),
            situational_anomaly=situational,
            reasons=sorted(set(reasons)),
        )
