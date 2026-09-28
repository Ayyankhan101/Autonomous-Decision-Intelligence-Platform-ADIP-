"""Confidence contract (plan §5.8): overall_confidence from severity/traffic/data-quality
ONLY; Laya answer_confidence is a separate gate (§5.8 correction, Invariant 11)."""
from __future__ import annotations

OVERALL_GATE = 0.6
# Interim until JevCity-fixture temperature fitting exists (ERRATA C3, Invariant 11).
LAYA_ANSWER_CONFIDENCE_GATE = 0.5


def overall_confidence(
    severity_confidence: float | None,
    traffic_confidence: float | None,
    data_quality_score: float,
) -> float:
    dq_confidence = 1.0 - data_quality_score
    parts = [
        p
        for p in (
            severity_confidence,
            traffic_confidence,
            dq_confidence,
        )
        if p is not None
    ]
    if not parts:
        return 0.0
    return min(parts)


def critical_signal_count(
    *,
    severity_crossed: bool,
    traffic_crossed: bool,
    situational_anomaly: bool,
) -> int:
    """Eligible sources only (Invariant 10): severity_model, traffic_impact_model,
    situational_anomaly_model. Laya is NOT eligible (ERRATA C5: heuristic/threshold
    components count as their own model when separately implemented + versioned)."""
    return sum([severity_crossed, traffic_crossed, situational_anomaly])
