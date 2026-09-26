import math

import pytest

from adip.stats import apply_temperature, confidence_max, logit, percentile


def test_percentile_linear_interpolation_matches_numpy_method_linear():
    # 4 samples: rank for p95 = 0.95 * 3 = 2.85 -> 3 + 0.85*(4-3)
    xs = [1.0, 2.0, 3.0, 4.0]
    assert percentile(xs, 95) == pytest.approx(3.85)
    assert percentile(xs, 50) == pytest.approx(2.5)
    assert percentile(xs, 0) == 1.0
    assert percentile(xs, 100) == 4.0


def test_percentile_accepts_unsorted_input():
    assert percentile([4.0, 1.0, 3.0, 2.0], 50) == pytest.approx(2.5)


def test_percentile_single_sample_and_bounds():
    assert percentile([7.0], 95) == 7.0
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1.0], 101)


def test_logit_roundtrip_and_clamping():
    assert apply_temperature(0.5, 1.0) == pytest.approx(0.5)
    assert apply_temperature(0.9, 1.0) == pytest.approx(0.9)
    # T < 1 sharpens: further from 0.5
    assert apply_temperature(0.9, 0.45) > 0.9
    assert apply_temperature(0.1, 0.45) < 0.1
    assert logit(1e-12) == pytest.approx(logit(1e-6))  # both clamp to EPS
    with pytest.raises(ValueError):
        apply_temperature(0.5, 0.0)


def test_confidence_max_is_two_sided():
    # the pre-fix ECE paired raw P(true) with decision correctness, which
    # penalised confident correct "no" answers (refund ECE 0.073 -> 0.689)
    assert confidence_max(0.07) == pytest.approx(0.93)
    assert confidence_max(0.9) == pytest.approx(0.9)
    assert confidence_max(0.5) == pytest.approx(0.5)


def test_temperature_is_monotone():
    ps = [i / 100 for i in range(101)]
    cal = [apply_temperature(p, 0.45) for p in ps]
    assert all(b >= a for a, b in zip(cal, cal[1:]))
    assert math.isclose(apply_temperature(0.5, 0.45), 0.5)
