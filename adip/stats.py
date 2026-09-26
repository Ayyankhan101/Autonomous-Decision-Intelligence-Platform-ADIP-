"""Metric math shared by evals/, benchmarks/, and serving/.

Every function here is dependency-free and covered by
``python3 evals/run_eval.py --selftest`` / ``tests/test_stats.py``.

percentile() is deliberately linear-interpolated (numpy ``method="linear"``)
so that p50/p95 reported by the eval runner, the latency harness, and the
serving summary are the same statistic. The pre-fix floor-rank variant in
serving/ and evals/ disagreed with benchmarks/ on identical samples
(p95 90.0 vs 95.5), which made cross-report comparisons meaningless.
"""

from __future__ import annotations

import math

EPS = 1e-6


def percentile(samples: list[float], pct: float) -> float:
    """Linear-interpolated percentile. Accepts unsorted input."""
    if not samples:
        raise ValueError("percentile() of empty sample list")
    if pct < 0 or pct > 100:
        raise ValueError(f"percentile must be in [0, 100], got {pct}")
    s = sorted(samples)
    if len(s) == 1:
        return s[0]
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def logit(p: float) -> float:
    p = min(max(p, EPS), 1.0 - EPS)
    return math.log(p / (1.0 - p))


def apply_temperature(p: float, T: float) -> float:
    """Temperature scaling on a single probability: sigmoid(logit(p) / T)."""
    if T <= 0:
        raise ValueError(f"temperature must be > 0, got {T}")
    return 1.0 / (1.0 + math.exp(-logit(p) / T))


def confidence_max(p: float) -> float:
    """Confidence of the predicted side of a one-sided noul P(true).

    ECE asks "does confidence in the *predicted* answer match accuracy?"; for a
    binary proposition that confidence is max(p, 1-p), not raw p. Pairing raw
    p(true) with decision correctness penalised correct "no" answers at p~0.07
    by ~0.93 each (refund ECE 0.073 -> 0.689 before the fix).
    """
    return max(p, 1.0 - p)


def apply_temperature_dist(dist: dict[str, float], T: float) -> dict[str, float]:
    """Temperature scaling on a categorical distribution: p_k^(1/T), renormalised.

    Equivalent to softmax(logits/T) for probs that came from a softmax, so the
    argmax is preserved for any T > 0 (scalar scaling cannot reorder classes).
    T < 1 sharpens, T > 1 flattens. Used for the department head's
    DEPT_TEMPERATURE calibration (evals/calibrate_dept.py fits it).
    """
    if T <= 0:
        raise ValueError(f"temperature must be > 0, got {T}")
    if not dist:
        raise ValueError("apply_temperature_dist() of empty distribution")
    scaled = {k: float(v) ** (1.0 / T) for k, v in dist.items()}
    total = sum(scaled.values())
    if total <= 0:
        raise ValueError("distribution has no mass to scale")
    return {k: v / total for k, v in scaled.items()}
