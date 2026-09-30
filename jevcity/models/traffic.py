"""Traffic-impact prediction — documented rule-based heuristic baseline (plan Phase 0 item 3:
no real traffic-response label; heuristic explicitly labeled as such, counts as an
independent signal per ERRATA C5). Task 3 extracts `traffic_delta` as the approved
synthetic label source; Task 5 replaces the model body with a trained regressor."""
from __future__ import annotations

from jevcity.schemas import ModelOutput, ModelStatus

_LEVEL_BUMP = {"free_flow": 0.05, "moderate": 0.15, "high": 0.3, "gridlock": 0.45}


def traffic_delta(features: dict) -> float:
    lanes = features.get("lanes_blocked") or 0
    level = features.get("traffic_level") or "moderate"
    vehicles = features.get("vehicles_involved") or 0
    return min(1.0, 0.15 * lanes + _LEVEL_BUMP.get(level, 0.15) + 0.03 * vehicles)


class TrafficModel:
    name = "traffic_impact_predictor"
    version = "traffic-heuristic-0.1.0"

    def __init__(self, fail: ModelStatus | None = None) -> None:
        self.fail = fail

    def predict(self, features: dict) -> ModelOutput:
        if self.fail is not None:
            return ModelOutput.failed(
                self.name, self.version, self.fail, error_code="MODEL_FAILURE"
            )
        level = features.get("traffic_level") or "moderate"
        factors = [
            f"lanes_blocked:{features.get('lanes_blocked') or 0}",
            f"traffic_level:{level}",
        ]
        confidence = 0.58 if level in ("high", "gridlock") else 0.62
        return ModelOutput(
            status=ModelStatus.OK,
            model_name=self.name,
            model_version=self.version,
            prediction=f"{traffic_delta(features):.2f}",
            confidence=confidence,
            latency_ms=3.0,
            explanation_factors=factors,
        )
