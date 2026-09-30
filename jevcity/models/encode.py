"""Fixed-order feature encoding shared by every Phase 2 model (plan §5.2).

Columns are frozen: changing order invalidates committed dataset + fitted models."""
from __future__ import annotations

CATEGORICAL: dict[str, tuple[str, ...]] = {
    "incident_type": ("accident", "fire", "flood", "traffic_spike"),
    "zone": ("north", "south", "east", "west", "central"),
    "weather": ("clear", "rain", "snow", "fog"),
    "traffic_level": ("free_flow", "moderate", "high", "gridlock"),
    "time_of_day_bucket": ("morning_peak", "day", "evening_peak", "night"),
    "severity_hint": ("minor", "moderate", "severe"),
}
NUMERIC = (
    "hour", "vehicles_involved", "injuries_reported", "lanes_blocked",
    "report_count", "zone_share", "type_share",
)


def columns() -> list[str]:
    names: list[str] = []
    for field, values in CATEGORICAL.items():
        names.extend(f"{field}={v}" for v in values)
        if field == "severity_hint":
            names.append("severity_hint=<none>")
    names.extend(f"num:{n}" for n in NUMERIC)
    return names


def encode(features: dict) -> list[float]:
    vec: list[float] = []
    for field, values in CATEGORICAL.items():
        got = features.get(field)
        vec.extend(1.0 if got == v else 0.0 for v in values)
        if field == "severity_hint":
            vec.append(0.0 if got in values else 1.0)
    vec.extend(float(features.get(name) or 0) for name in NUMERIC)
    return vec


def explain(features: dict, k: int = 3) -> list[str]:
    facts: list[str] = []
    for field, values in CATEGORICAL.items():
        got = features.get(field)
        if got in values:
            facts.append(f"{field}={got}")
    numeric_pairs = sorted(
        ((name, float(features.get(name) or 0)) for name in NUMERIC),
        key=lambda pair: pair[1],
        reverse=True,
    )
    facts.extend(f"{name}={value:g}" for name, value in numeric_pairs if value)
    if not facts:
        facts.append("baseline")
    return facts[:k]


def dq_vector(
    features: dict,
    *,
    contradiction_count: int,
    hard_error_count: int,
    soft_codes: list[str],
    status: str,
) -> list[float]:
    return encode(features) + [
        float(contradiction_count),
        float(hard_error_count),
        float(len(soft_codes)),
        1.0 if status == "hard_rejected" else 0.0,
        1.0 if "missing_injury_count" in soft_codes else 0.0,
        1.0 if "injected_data" in soft_codes else 0.0,
    ]
