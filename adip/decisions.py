"""Decision rules shared by the eval runner and the serving pipeline.

One rule per head, defined once: the eval scores what serving does.
"""

from __future__ import annotations

from adip.config import REFUND_THRESHOLD


def urgency_level(score: float, probabilities: dict | None = None) -> int:
    """Pick the urgency level with the most probability mass.

    Falls back to rounding the expected score when the runtime gives no
    per-level mass. The old rule was round(score) alone, which collapses to
    "1" on this model (scores cluster near 1.0): golden accuracy 0.48 vs
    0.56 for argmax, and the confidence of the *rounded* level is then
    paired with its correctness (ECE 0.163 -> 0.066).
    """
    if probabilities:
        keys = [k for k in probabilities if k.lstrip("-").isdigit()]
        if keys:
            best = max(keys, key=lambda k: float(probabilities[k]))
            return min(2, max(0, int(best)))
    return min(2, max(0, round(float(score))))


def refund_decision(p_calibrated: float) -> bool:
    """Shipped money-back call, on the calibrated probability."""
    return p_calibrated >= REFUND_THRESHOLD
