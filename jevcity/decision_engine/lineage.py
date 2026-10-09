"""Structured decision lineage (enhancement 3: hyper-explainable audit records).

Every decision gets a lineage block: normalised evidence terms on a common 0-1 scale,
the decisive policy clause chosen by fixed precedence, and a readable expression of the
form `+ [severity_model 0.85] - [resource_scarcity 0.70] -> CLAUSE R-CONTENTION-ESCALATE-01`.
Post-hoc explanation built from available signals/rules — not a causal trace of models.
"""
from __future__ import annotations

from jevcity.schemas import LayaBlock, LineageBlock, LineageTerm, Priority, Signals

_PRIORITY_WEIGHT = {
    Priority.CRITICAL: 1.0,
    Priority.HIGH: 0.75,
    Priority.MEDIUM: 0.5,
    Priority.LOW: 0.25,
}

_CLAUSE_PRECEDENCE = [
    "R-INPUT-REJECT-01",
    "R-MODEL-FAILURE-HOLD-01",
    "R-DATA-QUALITY-HOLD-01",
    "R-LOW-CONFIDENCE-HOLD-01",
    "R-CONTENTION-ESCALATE-01",
    "R-LAYA-CRITICAL-BLOCKED-INSUFFICIENT-SIGNALS-01",
    "R-LAYA-FALLBACK-POLICY-ONLY-01",
    "R-LAYA-MODEL-DEGRADED-01",
    "R-LAYA-LOW-ANSWER-CONFIDENCE-01",
    "R-LAYA-HUMAN-REVIEW-SUGGESTED-01",
    "R-AUTO-APPROVE-01",
]


def _clip(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def pick_clause(matched_rules: list[str]) -> str | None:
    """Decisive clause = highest-precedence matched rule (first rule as fallback)."""
    if not matched_rules:
        return None
    for rule in _CLAUSE_PRECEDENCE:
        if rule in matched_rules:
            return rule
    return matched_rules[0]


def build_lineage(
    signals: Signals,
    matched_rules: list[str],
    *,
    laya: LayaBlock | None = None,
    final_priority: Priority | None = None,
    assigned_resource_ids: list[str] | None = None,
    contention: bool = False,
) -> LineageBlock:
    terms: list[LineageTerm] = []

    sev = signals.severity
    if sev.confidence is not None:
        sev_score = _clip(sev.confidence)
        terms.append(
            LineageTerm(
                label="severity_model",
                score=sev_score,
                direction="positive",
                source="severity_model",
            )
        )
    elif sev.prediction:
        terms.append(
            LineageTerm(
                label="severity_model",
                score=_PRIORITY_WEIGHT.get(Priority(sev.prediction), 0.5),
                direction="positive",
                source="severity_model",
            )
        )
    else:
        terms.append(
            LineageTerm(
                label="severity_model", score=0.0, direction="neutral", source="severity_model"
            )
        )

    traffic = signals.traffic
    if traffic.predicted_congestion_delta is not None:
        delta = float(traffic.predicted_congestion_delta)
        direction = "positive" if delta > 0 else ("negative" if delta < 0 else "neutral")
        terms.append(
            LineageTerm(
                label="traffic_congestion",
                score=_clip(delta),
                direction=direction,
                source="traffic_model",
            )
        )
    else:
        terms.append(
            LineageTerm(
                label="traffic_congestion", score=0.0, direction="neutral", source="traffic_model"
            )
        )

    dq_score = signals.data_quality.data_quality_score
    terms.append(
        LineageTerm(
            label="data_quality_risk",
            score=_clip(dq_score),
            direction="negative" if dq_score > 0 else "neutral",
            source="anomaly_detector",
        )
    )

    if laya is not None and laya.suggested_priority is not None and final_priority is not None:
        agrees = laya.suggested_priority == final_priority
        conf = _clip(laya.answer_confidence_priority or 0.0)
        terms.append(
            LineageTerm(
                label="laya_advisory",
                score=conf,
                direction="positive" if agrees else "negative",
                source="laya_advisory",
            )
        )

    if assigned_resource_ids is not None:
        scarce = 1.0 if (contention or not assigned_resource_ids) else 0.0
        terms.append(
            LineageTerm(
                label="resource_scarcity",
                score=scarce,
                direction="negative" if scarce > 0 else "neutral",
                source="resource_pool",
            )
        )

    clause = pick_clause(matched_rules)
    symbols = {"positive": "+", "negative": "-", "neutral": "~"}
    expression = " ".join(
        f"{symbols[t.direction]} [{t.label} {t.score:.2f}]" for t in terms
    )
    if clause:
        expression = f"{expression} -> CLAUSE {clause}"

    return LineageBlock(terms=terms, clause_id=clause, expression=expression)
