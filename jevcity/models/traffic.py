"""Traffic-impact prediction — quantile gradient-boosting regressor (plan Phase 2).

`traffic_delta` stays the approved heuristic label source (sign-off item 3 / ERRATA C5);
the model body is a trained regressor. Confidence = 1 − (p90 − p10) interval width
(§5.8 uncertainty measure)."""
from __future__ import annotations

import time

from jevcity.models.encode import encode
from jevcity.models.ml_data import load_dataset
from jevcity.schemas import ModelOutput, ModelStatus

_LEVEL_BUMP = {"free_flow": 0.05, "moderate": 0.15, "high": 0.3, "gridlock": 0.45}
_CACHE: dict[str, object] = {}


def traffic_delta(features: dict) -> float:
    lanes = features.get("lanes_blocked") or 0
    level = features.get("traffic_level") or "moderate"
    vehicles = features.get("vehicles_involved") or 0
    return min(1.0, 0.15 * lanes + _LEVEL_BUMP.get(level, 0.15) + 0.03 * vehicles)


def _fitted():
    if "traffic" not in _CACHE:
        from sklearn.ensemble import GradientBoostingRegressor

        train, _ = load_dataset()
        features = [encode(row["features"]) for row in train]
        targets = [row["traffic_delta"] for row in train]
        point = GradientBoostingRegressor(n_estimators=60, max_depth=3, random_state=0)
        low = GradientBoostingRegressor(
            n_estimators=60, max_depth=3, random_state=0, loss="quantile", alpha=0.1
        )
        high = GradientBoostingRegressor(
            n_estimators=60, max_depth=3, random_state=0, loss="quantile", alpha=0.9
        )
        point.fit(features, targets)
        low.fit(features, targets)
        high.fit(features, targets)
        _CACHE["traffic"] = (point, low, high)
    return _CACHE["traffic"]


class TrafficModel:
    name = "traffic_impact_predictor"
    version = "traffic-gbr-1.0.0"

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
        point, low, high = _fitted()
        vector = [encode(features)]
        delta = min(1.0, max(0.0, float(point.predict(vector)[0])))
        p10 = float(low.predict(vector)[0])
        p90 = float(high.predict(vector)[0])
        width = max(0.0, p90 - p10)
        confidence = round(min(1.0, max(0.0, 1.0 - width)), 4)
        latency = (time.perf_counter() - t0) * 1000
        level = features.get("traffic_level") or "moderate"
        factors = [f"lanes_blocked:{features.get('lanes_blocked') or 0}",
                   f"traffic_level:{level}"]
        return ModelOutput(
            status=ModelStatus.OK,
            model_name=self.name,
            model_version=self.version,
            prediction=f"{delta:.2f}",
            confidence=confidence,
            latency_ms=round(latency, 3),
            explanation_factors=factors,
        )
