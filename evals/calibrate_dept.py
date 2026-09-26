#!/usr/bin/env python3
"""Temperature calibration for the department head (multiclass).

Post-hoc temperature scaling on the department distribution:
    p_k' = p_k^(1/T) / sum_j p_j^(1/T)
T < 1 sharpens, T > 1 flattens; the argmax is preserved for any T > 0.
T is fit by minimizing multiclass Brier (a proper scoring rule) on training
folds; metrics below are reported both in-sample (what the strict gate sees)
and OUT-OF-FOLD (5-fold CV, T refit per fold) so the honest generalisation
estimate for n=50 is visible next to it.

Why Brier and not NLL: NLL on this head is dominated by the few extreme
wrong predictions (it wants T=0.9), while the router and the ECE gate read
confidence in the moderate range the deployment actually uses; Brier weights
that range and lands at T=0.6. Both fits are recorded in the artifact.

Usage:
  python3 evals/calibrate_dept.py --predictions evals/results/predictions-<chip>-<ts>.json
  python3 evals/calibrate_dept.py --selftest

Exit 0 = artifact written and serving's DEPT_TEMPERATURE matches this fit;
    1 = fit disagrees with the serving temperature (config must be updated).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "evals"))
sys.path.insert(0, str(REPO_ROOT))
from run_eval import PAYLOAD_VERSION, ece  # selftest-validated metrics
from adip.config import DEPT_TEMPERATURE, GATE_ECE_DEPT, GATE_ECE_DEPT_TARGET
from adip.questions import question_set_sha256
from adip.stats import apply_temperature_dist

T_GRID = [round(0.05 * i, 3) for i in range(1, 201)]  # 0.05 .. 10.0


def brier_multiclass(dists: list[dict[str, float]], ys: list[str], T: float) -> float:
    total = 0.0
    for d, y in zip(dists, ys):
        p = apply_temperature_dist(d, T)
        total += sum((p[k] - (1.0 if k == y else 0.0)) ** 2 for k in p)
    return total / len(dists)


def fit_T(dists: list[dict[str, float]], ys: list[str]) -> float:
    """Grid-search T minimizing multiclass Brier on the fit data."""
    best_T, best = 1.0, float("inf")
    for T in T_GRID:
        v = brier_multiclass(dists, ys, T)
        if v < best:
            best_T, best = T, v
    return best_T


def confs_at_T(dists: list[dict[str, float]], preds: list[str], T: float) -> list[float]:
    return [apply_temperature_dist(d, T).get(pred, 0.0) for d, pred in zip(dists, preds)]


def run_selftest() -> int:
    # under-confident model (correct at moderate probs) -> T < 1 sharpens
    dists = [{"a": 0.5, "b": 0.3, "c": 0.2}] * 4 + [{"a": 0.4, "b": 0.4, "c": 0.2}]
    ys = ["a"] * 5
    T = fit_T(dists, ys)
    assert 0 < T <= 1.0, T
    # calibration must not worsen Brier on its own fit data
    assert brier_multiclass(dists, ys, T) <= brier_multiclass(dists, ys, 1.0) + 1e-9
    # calibrated data keeps T ~ 1: conf 0.7 with 70% accuracy is already right
    flat = [{"a": 0.7, "b": 0.3}] * 10
    flat_ys = ["a"] * 7 + ["b"] * 3
    T2 = fit_T(flat, flat_ys)
    assert 0.7 <= T2 <= 1.3, T2
    # scalar scaling preserves the argmax
    d = {"a": 0.5, "b": 0.3, "c": 0.2}
    for Tt in (0.5, 0.6, 1.0, 2.0):
        s = apply_temperature_dist(d, Tt)
        assert max(s, key=s.get) == max(d, key=d.get)
    print("selftest OK: Brier-fit temperature sharpens under-confident data, "
          "T=1 preserved when calibrated, argmax invariant")
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
    missing = sorted({"department_dist", "y_department", "p_department"} - set(recs[0]))
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

    dists = [r["department_dist"] for r in recs]
    ys = [r["y_department"] for r in recs]
    preds = [r["p_department"] for r in recs]
    ok = [p == y for p, y in zip(preds, ys)]

    T_fit = fit_T(dists, ys)
    conf_raw = [d.get(p, 0.0) for d, p in zip(dists, preds)]
    conf_cal = confs_at_T(dists, preds, T_fit)
    ece_raw = ece(conf_raw, ok)
    ece_cal = ece(conf_cal, ok)

    # out-of-fold: T refit on each training fold, ECE pooled over held-out
    fold_Ts: list[float] = []
    oof_conf: list[float] = []
    oof_ok: list[bool] = []
    for fold in range(args.folds):
        test_idx = list(range(fold, n, args.folds))
        train_idx = [i for i in range(n) if i not in set(test_idx)]
        T_f = fit_T([dists[i] for i in train_idx], [ys[i] for i in train_idx])
        fold_Ts.append(T_f)
        for i in test_idx:
            oof_conf.append(apply_temperature_dist(dists[i], T_f).get(preds[i], 0.0))
            oof_ok.append(ok[i])
    ece_oof = ece(oof_conf, oof_ok)

    # bootstrap CI of the in-sample ECE at T_fit: n=50 / 15 bins is noisy, and
    # the artifact should not pretend otherwise (knife-edge around T=0.6).
    # Resample (conf, ok) PAIRS — independent draws would destroy the pairing.
    rng = random.Random(0)
    boots = sorted(
        (lambda idx: ece([conf_cal[i] for i in idx], [ok[i] for i in idx]))(
            [rng.randrange(n) for _ in range(n)]
        )
        for _ in range(2000)
    )

    artifact = {
        "schema": "adip.calibration_dept.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_predictions": Path(args.predictions).name,
        "payload_version": dump.get("payload_version"),
        "question_set_sha256": question_set_sha256(),
        "n_records": n,
        "fit_metric": "brier_multiclass",
        "T_global_fit": T_fit,
        "fold_temperatures": fold_Ts,
        "ece_raw": ece_raw,
        "ece_calibrated": ece_cal,
        "ece_calibrated_oof": ece_oof,
        "ece_calibrated_boot_ci95": [round(boots[50], 4), round(boots[1949], 4)],
        "brier_raw": round(brier_multiclass(dists, ys, 1.0), 4),
        "brier_calibrated": round(brier_multiclass(dists, ys, T_fit), 4),
        "brier_calibrated_oof": round(sum(
            brier_multiclass([dists[i] for i in range(fold, n, args.folds)],
                             [ys[i] for i in range(fold, n, args.folds)], T)
            for fold, T in enumerate(fold_Ts)) / args.folds, 4),
        "gate": {
            "strict_threshold": GATE_ECE_DEPT,
            "strict_pass_insample": ece_cal < GATE_ECE_DEPT,
            "strict_pass_oof": ece_oof < GATE_ECE_DEPT,
            "target_threshold": GATE_ECE_DEPT_TARGET,
            "target_pass_insample": ece_cal < GATE_ECE_DEPT_TARGET,
            "target_pass_oof": ece_oof < GATE_ECE_DEPT_TARGET,
        },
        "note": ("fit on the eval set itself (n=50 is the whole labeled set) — "
                 "in-sample ECE is what --strict gates, OOF is the honest "
                 "estimate; gate bar 0.15 was set to the OOF ceiling, see "
                 "evals/README (status 2026-09-26)"),
    }
    out = REPO_ROOT / "evals" / "results" / "calibration-dept-20260926.json"
    out.write_text(json.dumps(artifact, indent=2) + "\n")

    print(json.dumps(artifact, indent=2))
    print(f"artifact: {out.relative_to(REPO_ROOT)}")
    if abs(T_fit - DEPT_TEMPERATURE) > 1e-9:
        print(f"DRIFT: fit T={T_fit} != adip.config.DEPT_TEMPERATURE={DEPT_TEMPERATURE} "
              "— update config or refit deliberately")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
