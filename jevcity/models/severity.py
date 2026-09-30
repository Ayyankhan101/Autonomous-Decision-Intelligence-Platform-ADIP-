"""Severity/risk prediction — calibrated gradient boosting (plan Phase 2).

Label = documented hint mapping from `tools/gen_ml_dataset.py`; confidence =
CalibratedClassifierCV sigmoid probability of the predicted class (§5.8)."""
from __future__ import annotations

import time
from pathlib import Path

from jevcity.models.encode import encode, explain
from jevcity.models.ml_data import load_dataset
from jevcity.schemas import ModelOutput, ModelStatus

DATASET = Path("datasets/jevcity/ml/dataset.jsonl")
_CACHE: dict[str, object] = {}


def _fitted():
    if "severity" not in _CACHE:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import GradientBoostingClassifier

        train, _ = load_dataset(DATASET)
        features = [encode(row["features"]) for row in train]
        labels = [row["severity"] for row in train]
        clf = CalibratedClassifierCV(
            GradientBoostingClassifier(n_estimators=60, max_depth=3, random_state=0),
            method="sigmoid",
            cv=3,
        )
        clf.fit(features, labels)
        _CACHE["severity"] = clf
    return _CACHE["severity"]


class SeverityModel:
    name = "severity_predictor"
    version = "sev-gb-1.0.0"

    def __init__(self, fail: ModelStatus | None = None) -> None:
        self.fail = fail
        if fail is None:
            _fitted()

    def predict(self, features: dict) -> ModelOutput:
        if self.fail is not None:
            return ModelOutput.failed(
                self.name, self.version, self.fail, error_code="MODEL_FAILURE"
            )
        t0 = time.perf_counter()
        clf = _fitted()
        vector = [encode(features)]
        probabilities = clf.predict_proba(vector)[0]
        classes = list(clf.classes_)
        best = max(range(len(classes)), key=lambda i: probabilities[i])
        latency = (time.perf_counter() - t0) * 1000
        return ModelOutput(
            status=ModelStatus.OK,
            model_name=self.name,
            model_version=self.version,
            prediction=str(classes[best]),
            confidence=round(min(max(float(probabilities[best]), 0.0), 1.0), 4),
            latency_ms=round(latency, 3),
            explanation_factors=explain(features),
        )
