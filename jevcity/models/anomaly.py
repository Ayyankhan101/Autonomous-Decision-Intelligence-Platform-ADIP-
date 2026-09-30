"""Anomaly detection — supervised data-quality score + IsolationForest situational flag
(plan Phase 2 split). Conservative on failure: model failure or hard-rejected input
forces worst-quality data (fail closed, Invariant 4/12)."""
from __future__ import annotations

from pathlib import Path

from jevcity.models.encode import dq_vector, encode
from jevcity.models.ml_data import load_dataset
from jevcity.schemas import AnomalyOutput, EventEnvelope, ModelStatus, ValidationResult

DATASET = Path("datasets/jevcity/ml/dataset.jsonl")
_CACHE: dict[str, object] = {}


def _training_vectors() -> tuple[list[list[float]], list[int], list[list[float]]]:
    train, _ = load_dataset(DATASET)
    dq_x: list[list[float]] = []
    dq_y: list[int] = []
    iso_x: list[list[float]] = []
    for row in train:
        dq_x.append(dq_vector(
            row["features"],
            contradiction_count=row["contradictions"],
            hard_error_count=row["validation"]["hard"],
            soft_codes=row["validation"]["soft_codes"],
            status=row["validation"]["status"],
        ))
        dq_y.append(row["dq_label"])
        iso_x.append(encode(row["features"]))
    return dq_x, dq_y, iso_x


def _fitted():
    if "anomaly" not in _CACHE:
        from sklearn.ensemble import IsolationForest
        from sklearn.linear_model import LogisticRegression

        dq_x, dq_y, iso_x = _training_vectors()
        logistic = LogisticRegression(max_iter=500, random_state=0)
        logistic.fit(dq_x, dq_y)
        iso = IsolationForest(contamination=0.1, random_state=0)
        iso.fit(iso_x)
        _CACHE["anomaly"] = (logistic, iso)
    return _CACHE["anomaly"]


class AnomalyDetector:
    name = "anomaly_detector"
    version = "anom-ml-1.0.0"

    def __init__(self, fail: ModelStatus | None = None) -> None:
        self.fail = fail
        if fail is None:
            _fitted()

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
        logistic, iso = _fitted()
        vector = dq_vector(
            features,
            contradiction_count=len(contradictions),
            hard_error_count=len(validation.hard_errors),
            soft_codes=[w.code for w in validation.soft_warnings],
            status=validation.validation_status.value,
        )
        score = float(logistic.predict_proba([vector])[0][1])
        reasons = [f"dq_model_score:{score:.2f}"]
        if contradictions:
            reasons.extend(sorted(set(contradictions))[:3])
        soft_codes = {w.code for w in validation.soft_warnings}
        if "injected_data" in soft_codes:
            score = max(score, 0.5)
            reasons.append("injected_data")
        if validation.validation_status.value == "hard_rejected":
            score = 1.0
            reasons.append("hard_invalid_input")
        situational = bool(iso.predict([encode(features)])[0] == -1)
        if situational:
            reasons.append("situational_isolation_forest")
        return AnomalyOutput(
            data_quality_anomaly=score >= 0.5,
            data_quality_score=min(1.0, score),
            situational_anomaly=situational,
            reasons=sorted(set(reasons))[:4],
        )
