from __future__ import annotations

from pathlib import Path

from jevcity.models.ml_data import load_dataset
from jevcity.models.severity import SeverityModel
from jevcity.schemas import ModelStatus

DATASET = Path("datasets/jevcity/ml/dataset.jsonl")
PRIORITY_LABELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_load_dataset_split():
    train, held = load_dataset(DATASET)
    assert train and held
    assert len(train) + len(held) >= 250
    assert len(held) >= 40


def test_severity_predict_valid_and_deterministic():
    model = SeverityModel()
    features = {"incident_type": "accident", "zone": "north", "hour": 8,
                "time_of_day_bucket": "morning_peak", "weather": "rain",
                "traffic_level": "high", "severity_hint": "severe",
                "vehicles_involved": 4, "injuries_reported": 3, "lanes_blocked": 2,
                "report_count": 1}
    a = model.predict(features)
    b = model.predict(features)
    assert a.status is ModelStatus.OK
    assert a.prediction in PRIORITY_LABELS
    assert a.confidence is not None and 0.0 <= a.confidence <= 1.0
    assert a.model_version == "sev-gb-1.0.0"
    assert a.latency_ms >= 0
    assert a.explanation_factors
    assert (a.prediction, a.confidence) == (b.prediction, b.confidence)


def test_severity_empty_features_still_ok():
    out = SeverityModel().predict({})
    assert out.status is ModelStatus.OK
    assert out.prediction in PRIORITY_LABELS


def test_severity_fail_param_preserved():
    out = SeverityModel(fail=ModelStatus.ERROR).predict({})
    assert out.status is ModelStatus.ERROR
    assert out.error_code == "MODEL_FAILURE"
    assert out.prediction is None


def test_severity_heldout_accuracy_floor():
    train, held = load_dataset(DATASET)
    model = SeverityModel()
    correct = sum(
        1 for row in held
        if model.predict(row["features"]).prediction == row["severity"]
    )
    assert correct / len(held) >= 0.65, f"held-out accuracy {correct / len(held):.3f}"

from jevcity.models.traffic import TrafficModel


def test_traffic_trained_valid_and_deterministic():
    model = TrafficModel()
    features = {"lanes_blocked": 2, "traffic_level": "high", "vehicles_involved": 4,
                "incident_type": "accident", "zone": "north", "hour": 8,
                "time_of_day_bucket": "morning_peak", "weather": "clear",
                "severity_hint": "moderate", "report_count": 1}
    a = model.predict(features)
    b = model.predict(features)
    assert a.status is ModelStatus.OK
    assert a.model_version == "traffic-gbr-1.0.0"
    assert a.prediction is not None and 0.0 <= float(a.prediction) <= 1.0
    assert a.confidence is not None and 0.0 <= a.confidence <= 1.0
    assert (a.prediction, a.confidence) == (b.prediction, b.confidence)
    assert a.explanation_factors


def test_traffic_heldout_mae_floor():
    from jevcity.models.ml_data import load_dataset

    _, held = load_dataset()
    model = TrafficModel()
    errors = [abs(float(model.predict(r["features"]).prediction) - r["traffic_delta"])
              for r in held]
    mae = sum(errors) / len(errors)
    assert mae <= 0.1, f"held-out MAE {mae:.4f}"


def test_traffic_fail_param_preserved():
    out = TrafficModel(fail=ModelStatus.TIMEOUT).predict({})
    assert out.status is ModelStatus.TIMEOUT
