from __future__ import annotations

from jevcity.schemas import ModelOutput, ModelStatus


class FixedSeverity:
    name = "severity_predictor"
    version = "sev-test-0.0.1"

    def __init__(self, prediction: str, confidence: float, status: ModelStatus = ModelStatus.OK):
        self.prediction = prediction
        self.confidence = confidence
        self.status = status

    def predict(self, features: dict) -> ModelOutput:
        if self.status != ModelStatus.OK:
            return ModelOutput.failed(
                self.name, self.version, self.status, error_code="MODEL_FAILURE"
            )
        return ModelOutput(
            status=ModelStatus.OK,
            model_name=self.name,
            model_version=self.version,
            prediction=self.prediction,
            confidence=self.confidence,
            latency_ms=1.0,
        )


class FixedTraffic:
    name = "traffic_impact_predictor"
    version = "traffic-test-0.0.1"

    def __init__(self, delta: float, confidence: float, status: ModelStatus = ModelStatus.OK):
        self.delta = delta
        self.confidence = confidence
        self.status = status

    def predict(self, features: dict) -> ModelOutput:
        if self.status != ModelStatus.OK:
            return ModelOutput.failed(
                self.name, self.version, self.status, error_code="MODEL_FAILURE"
            )
        return ModelOutput(
            status=ModelStatus.OK,
            model_name=self.name,
            model_version=self.version,
            prediction=f"{self.delta:.2f}",
            confidence=self.confidence,
            latency_ms=1.0,
        )
