"""Traffic-impact prediction — documented rule-based heuristic baseline (plan Phase 0 item 3:
no real traffic-response label; heuristic explicitly labeled as such, counts as an
independent signal per ERRATA C5)."""
from __future__ import annotations

from jevcity.schemas import ModelOutput, ModelStatus

_LEVEL_BUMP = {"free_flow": 0.05, "moderate": 0.15, "high": 0.3, "gridlock": 0.45}


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

        lanes = features.get("lanes_blocked") or 0
        level = features.get("traffic_level") or "moderate"
        vehicles = features.get("vehicles_involved") or 0
        delta = min(1.0, 0.15 * lanes + _LEVEL_BUMP.get(level, 0.15) + 0.03 * vehicles)
        factors = [f"lanes_blocked:{lanes}", f"traffic_level:{level}"]
        confidence = 0.58 if level in ("high", "gridlock") else 0.62
        return ModelOutput(
            status=ModelStatus.OK,
            model_name=self.name,
            model_version=self.version,
            prediction=f"{delta:.2f}",
            confidence=confidence,
            latency_ms=3.0,
            explanation_factors=factors,
        )
