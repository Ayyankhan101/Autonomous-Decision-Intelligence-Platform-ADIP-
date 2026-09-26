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

Exit 0 = artifact written and serving's REFUND_TEMPERATURE matches this fit;
    1 = fit disagrees with the serving temperature (config must be updated).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "evals"))
sys.path.insert(0, str(REPO_ROOT))
from run_eval import PAYLOAD_VERSION, ece, brier_binary  # selftest-validated metrics
from adip.config import GATE_ECE_REFUND, REFUND_TEMPERATURE, REFUND_THRESHOLD

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
    if args.folds < 2:
        ap.error(f"--folds must be >= 2, got {args.folds} (1 fold has no held-out data)")

    try:
        dump = json.loads(Path(args.predictions).read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"{args.predictions}: not valid JSON ({e})")
    recs = dump.get("records") if isinstance(dump, dict) else None
    if not recs:
        raise SystemExit(f"{args.predictions}: no records[] — refusing to calibrate "
                         "an empty or malformed predictions dump")
    missing = sorted({"refund_p", "y_refund"} - set(recs[0]))
    if missing:
        raise SystemExit(f"{args.predictions}: records missing {missing}")
    # provenance: a T fit on a different payload_version than the serving
    # pipeline sends would silently ship a calibration for the wrong task
    src_payload = dump.get("payload_version")
    if src_payload is not None and src_payload != PAYLOAD_VERSION:
        raise SystemExit(f"{args.predictions}: payload_version {src_payload} != "
                         f"runner's {PAYLOAD_VERSION}; refit from a current dump")
    n = len(recs)
    if args.folds > n:
        ap.error(f"--folds {args.folds} > n_records {n} (empty folds divide by zero)")
    ps_raw = [r["refund_p"] for r in recs]
    ys = [bool(r["y_refund"]) for r in recs]
    correct = [bool(r["refund_p"] >= REFUND_THRESHOLD) == y for r, y in zip(recs, ys)]

    n = len(ps_raw)
    fold_size = n // args.folds
    folds = [list(range(i * fold_size, (i + 1) * fold_size)) for i in range(args.folds - 1)]
    folds.append(list(range((args.folds - 1) * fold_size, n)))
    # OOF alignment contract: folds must be ascending and disjoint so oof_cal
    # lines up index-for-index with `correct`/`ys` below. shuffle anything here
    # and the ECE pairs calibrated p with the wrong label.
    assert [i for f in folds for i in f] == list(range(n)), "folds must partition 0..n-1 in order"

    oof_cal, fold_Ts = [], []
    for fold in folds:
        train = [i for i in range(n) if i not in fold]
        T = fit_T([ps_raw[i] for i in train], [ys[i] for i in train])
        fold_Ts.append(T)
        oof_cal.extend(apply_T([ps_raw[i] for i in fold], T))

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
        "payload_version": dump.get("payload_version"),
        "n_records": n,
        "refund_accuracy": round(acc, 4),
        # `raw` = uncalibrated model output on all n records (nothing is fit,
        # so no CV is needed or possible); `calibrated` = out-of-fold, each
        # record scored by a T fit without it. The old `_oof` suffix on the raw
        # pair implied cross-validation on the baseline side.
        "ece_raw": ece_raw,
        "ece_calibrated_oof": ece_cal,
        "brier_raw": brier_raw,
        "brier_calibrated_oof": brier_cal,
        "fold_temperatures": fold_Ts,
        "T_global_fit": T_global,
        "recipe": f"p_cal = sigmoid(logit(p) / {T_global})",
        "gate_pass_after_calibration": ece_cal < GATE_ECE_REFUND,
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
    # round-trip check: an artifact that does not re-parse is a broken artifact
    json.loads(out.read_text())
    print(f"saved: {out.relative_to(REPO_ROOT)}")
    if abs(T_global - REFUND_TEMPERATURE) > 1e-9:
        print(f"ACTION REQUIRED: serving applies adip.config.REFUND_TEMPERATURE="
              f"{REFUND_TEMPERATURE}, but this fit produced T={T_global}. Refit "
              "changed the shipped calibration - update adip/config.py "
              "(tests/test_config.py asserts the two match).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
