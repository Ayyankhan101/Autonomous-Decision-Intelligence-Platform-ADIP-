from __future__ import annotations

import time

from jevcity.api.app import build_engine
from jevcity.models.wrapper import AnomalyWrapper, ModelWrapper
from jevcity.schemas import AnomalyOutput, ModelOutput, ModelStatus


class _SlowModel:
    name = "slow"
    version = "v0"

    def predict(self, features: dict) -> ModelOutput:
        time.sleep(1.0)
        return ModelOutput(status=ModelStatus.OK, model_name=self.name,
                           model_version=self.version, prediction="LOW",
                           confidence=0.5, latency_ms=1000.0)


class _BoomModel:
    name = "boom"
    version = "v0"

    def predict(self, features: dict) -> ModelOutput:
        raise RuntimeError("fit exploded")


class _OkModel:
    name = "ok"
    version = "v0"

    def predict(self, features: dict) -> ModelOutput:
        return ModelOutput(status=ModelStatus.OK, model_name=self.name,
                           model_version=self.version, prediction="HIGH",
                           confidence=0.9, latency_ms=1.0)


def test_wrapper_timeout_status():
    out = ModelWrapper(_SlowModel(), timeout_s=0.05).predict({})
    assert out.status is ModelStatus.TIMEOUT
    assert out.error_code == "MODEL_TIMEOUT"
    assert out.prediction is None


def test_wrapper_exception_status():
    out = ModelWrapper(_BoomModel(), timeout_s=0.5).predict({})
    assert out.status is ModelStatus.ERROR
    assert out.error_code == "MODEL_EXCEPTION"


def test_wrapper_ok_measures_latency():
    out = ModelWrapper(_OkModel(), timeout_s=0.5).predict({})
    assert out.status is ModelStatus.OK
    assert out.prediction == "HIGH"
    assert out.latency_ms >= 0


def test_anomaly_wrapper_fail_closed_on_timeout():
    class _SlowAnomaly:
        name = "slow-anom"
        version = "v0"

        def predict(self, *args, **kwargs) -> AnomalyOutput:
            time.sleep(1.0)
            return AnomalyOutput(data_quality_anomaly=False, data_quality_score=0.0,
                                 situational_anomaly=False)

    out = AnomalyWrapper(_SlowAnomaly(), timeout_s=0.05).predict({}, [], None, [])
    assert out.data_quality_score == 1.0
    assert out.data_quality_anomaly is True
    assert out.reasons == ["anomaly_model_failure"]


def test_engine_wraps_models():
    engine = build_engine()
    from jevcity.models.wrapper import AnomalyWrapper as AW
    from jevcity.models.wrapper import ModelWrapper as MW

    assert isinstance(engine.severity, MW)
    assert isinstance(engine.traffic, MW)
    assert isinstance(engine.anomaly, AW)
    assert engine.severity.name == "severity_predictor"
    assert engine.severity.version == "sev-gb-1.0.0"
