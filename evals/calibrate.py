#!/usr/bin/env python3
"""Temperature calibration for ADIP eval predictions (blueprint section 9 lever).

Post-hoc temperature scaling on the refund noul probability:
    p_cal = sigmoid(logit(p) / T)
T < 1 sharpens, T > 1 flattens. T is fit by minimizing negative log-likelihood
on training folds; metrics below are computed OUT-OF-FOLD (5-fold CV) so the
improvement estimate is honest for n=50 — no metric is computed on the data
its T was fit to.

Usage:
  python3 evals/calibrate.py --predictions evals/results/predictions-<chip>-<ts>.json
  python3 evals/calibrate.py --selftest

Exit 0 always (analysis tool); prints a JSON summary.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "evals"))
from run_eval import ece, brier_binary  # selftest-validated metrics

EPS = 1e-6
T_GRID = [round(0.05 * i, 3) for i in range(1, 201)]  # 0.05 .. 10.0


def logit(p: float) -> float:
    p = min(max(p, EPS), 1.0 - EPS)
    return math.log(p / (1.0 - p))


def apply_T(ps: list[float], T: float) -> list[float]:
    return [1.0 / (1.0 + math.exp(-logit(p) / T)) for p in ps]


def nll(ps: list[float], ys: list[bool]) -> float:
    total = 0.0
    for p, y in zip(ps, ys):
        p = min(max(p, EPS), 1.0 - EPS)
        total += -math.log(p) if y else -math.log(1.0 - p)
    return total / len(ps)


def fit_T(ps: list[float], ys: list[bool]) -> float:
    """Grid-search T minimizing NLL (convex in T for this transform family)."""
    best_T, best_nll = 1.0, float("inf")
    for T in T_GRID:
        v = nll(apply_T(ps, T), ys)
        if v < best_nll:
            best_T, best_nll = T, v
    return best_T


def run_selftest() -> int:
    # overconfident correct-ish model: T < 1 should sharpen, T > 1 flatten
    ps = [0.99, 0.98, 0.40, 0.30]
    ys = [True, True, False, False]
    # flat-ish truth: accuracy 1.0 with moderate confidences -> optimal T < 1
    T = fit_T(ps, ys)
    assert 0 < T <= 1.0, T
    # calibration must not worsen NLL on its own fit data
    assert nll(apply_T(ps, T), ys) <= nll(ps, ys) + 1e-9
    # perfectly calibrated data keeps T ~ 1
    ps2 = [0.8] * 5
    ys2 = [True, True, True, True, False]
    T2 = fit_T(ps2, ys2)
    assert 0.7 <= T2 <= 1.3, T2
    print("selftest OK: temperature fit reduces NLL on fit data; T=1 preserved when calibrated")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--predictions", default=None)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()
    if not args.predictions:
        ap.error("--predictions is required (or use --selftest)")

    dump = json.loads(Path(args.predictions).read_text())
    recs = dump["records"]
    ps_raw = [r["refund_p"] for r in recs]
    ys = [bool(r["y_refund"]) for r in recs]
    correct = [bool(r["refund_p"] >= 0.5) == y for r, y in zip(recs, ys)]

    n = len(ps_raw)
    fold_size = n // args.folds
    folds = [list(range(i * fold_size, (i + 1) * fold_size)) for i in range(args.folds - 1)]
    folds.append(list(range((args.folds - 1) * fold_size, n)))

    oof_raw, oof_cal, fold_Ts = [], [], []
    for fold in folds:
        train = [i for i in range(n) if i not in fold]
        T = fit_T([ps_raw[i] for i in train], [ys[i] for i in train])
        fold_Ts.append(T)
        for i in fold:
            oof_raw.append(ps_raw[i])
            oof_cal.append(1.0 / (1.0 + math.exp(-logit(ps_raw[i]) / T)))

    # global T fit on all data (for production reference; NOT used for the CV numbers)
    T_global = fit_T(ps_raw, ys)

    # Corrected semantics (matches run_eval fix): ECE on decision confidence
    # max(p, 1-p); Brier on P(true) vs the true label.
    conf_raw = [max(p, 1.0 - p) for p in ps_raw]
    ece_raw = ece(conf_raw, correct)
    ece_cal = ece([max(p, 1.0 - p) for p in oof_cal], correct)
    brier_raw = brier_binary(ps_raw, ys)
    brier_cal = brier_binary(oof_cal, ys)
    acc = sum(correct) / n

    summary = {
        "schema": "adip.calibration.v1",
        "source": str(Path(args.predictions).name),
        "n_records": n,
        "refund_accuracy": round(acc, 4),
        "ece_raw_oof": ece_raw,
        "ece_calibrated_oof": ece_cal,
        "brier_raw_oof": brier_raw,
        "brier_calibrated_oof": brier_cal,
        "fold_temperatures": fold_Ts,
        "T_global_fit": T_global,
        "recipe": f"p_cal = sigmoid(logit(p) / {T_global})",
        "gate_pass_after_calibration": ece_cal < 0.05,
        "honesty_note": (
            "Out-of-fold CV metrics; each record's calibrated p uses a T fit "
            "without it. T_global is the production recipe but overfits this "
            "n=50 by construction - refit on a held-out calibration set "
            "before trusting the gate verdict for external claims."
        ),
    }
    print(json.dumps(summary, indent=2))
    out = REPO_ROOT / "evals" / "results" / f"calibration-{Path(args.predictions).stem}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"saved: {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
