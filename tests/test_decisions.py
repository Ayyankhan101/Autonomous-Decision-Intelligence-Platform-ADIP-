"""Decision rules: argmax urgency, calibrated refund threshold."""

from __future__ import annotations

from adip.config import REFUND_THRESHOLD
from adip.decisions import refund_decision, urgency_level


def test_urgency_prefers_probability_mass_over_rounded_score():
    # score 1.1655 rounds to 1, but level 2 holds the mass (golden TICKET-0001)
    assert urgency_level(1.1655, {"0": 0.277, "1": 0.280, "2": 0.443}) == 2
    assert urgency_level(0.9, {"0": 0.80, "1": 0.15, "2": 0.05}) == 0


def test_urgency_falls_back_to_rounding_without_mass():
    assert urgency_level(0.4) == 0
    assert urgency_level(1.49) == 1
    assert urgency_level(2.0) == 2
    assert urgency_level(99.0) == 2   # clamped
    assert urgency_level(-3.0) == 0


def test_urgency_ignores_non_numeric_keys():
    assert urgency_level(1.0, {"__meta__": 0.99, "1": 0.6, "2": 0.4}) == 1


def test_refund_decision_threshold_boundary():
    assert refund_decision(REFUND_THRESHOLD) is True
    assert refund_decision(REFUND_THRESHOLD - 1e-9) is False
    assert refund_decision(0.99) is True
