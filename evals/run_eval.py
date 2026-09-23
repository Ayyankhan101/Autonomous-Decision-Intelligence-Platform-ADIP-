#!/usr/bin/env python3
"""ADIP eval runner: scores laya-mlx predictions against the golden set.

Metrics (blueprint section 9):
  * macro-F1 + per-class P/R/F1 for the department choice
  * accuracy for all three labels
  * ECE (15 bins) + Brier for department and refund; ECE for urgency on the
    predicted level's probability mass
  * department confusion matrix
  * determinism: two full passes, answers JSON hashed and compared
  * per-decision latency summary

Dependency-free (hand-rolled metrics, validated by --selftest).

Usage:
  python3 evals/run_eval.py --selftest
  .venv-bench/bin/python evals/run_eval.py --file datasets/golden-set/golden-template.json
  .venv-bench/bin/python evals/run_eval.py --file datasets/golden-set/golden-v1.0.json --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "evals" / "results"

DEPTS = ["billing", "technical", "sales", "account"]
URGENCY_LEVELS = [0, 1, 2]
ECE_BINS = 15

# The question set sent to the model; must equal the golden set's question_set.
QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this request?",
        "criteria": {
            "billing": "invoices, payments, refunds, duplicate charges",
            "technical": "bugs, outages, integration failures",
            "sales": "new purchases, upgrades, pricing",
            "account": "login, password, profile, subscription status, data requests",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this request?",
        "criteria": ["not urgent", "soon", "critical"],
    },
    "refund": {
        "type": "noul",
        "instructions": "Does the customer ask for money back?",
    },
}


# ---------------------------------------------------------------------------
# metrics math (validated by --selftest)
# ---------------------------------------------------------------------------

def prf_one(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return prec, rec, f1


def macro_f1(y_true: list[str], y_pred: list[str]) -> dict:
    tps: dict[str, int] = {c: 0 for c in DEPTS}
    fps: dict[str, int] = {c: 0 for c in DEPTS}
    fns: dict[str, int] = {c: 0 for c in DEPTS}
    for t, p in zip(y_true, y_pred):
        if p == t:
            tps[t] += 1
        else:
            fps[p] += 1
            fns[t] += 1
    per_class = {}
    for c in DEPTS:
        prec, rec, f1 = prf_one(tps[c], fps[c], fns[c])
        per_class[c] = {
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "support": tps[c] + fns[c],
        }
    # macro over classes present in y_true (support > 0); the frozen 50-ticket
    # set guarantees all four departments, so this equals the all-class macro there
    present = [c for c in DEPTS if per_class[c]["support"] > 0]
    macro = statistics.fmean(per_class[c]["f1"] for c in present) if present else 0.0
    return {"macro_f1": round(macro, 4), "per_class": per_class}


def confusion(y_true: list[str], y_pred: list[str]) -> dict:
    cm = {t: {p: 0 for p in DEPTS} for t in DEPTS}
    for t, p in zip(y_true, y_pred):
        cm[t][p] += 1
    return cm


def ece(confidences: list[float], corrects: list[bool], bins: int = ECE_BINS) -> float:
    """Expected calibration error over equal-width bins on [0,1]."""
    if not confidences:
        return 0.0
    n = len(confidences)
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not idx:
            continue
        bin_conf = statistics.fmean(confidences[i] for i in idx)
        bin_acc = statistics.fmean(1.0 if corrects[i] else 0.0 for i in idx)
        total += (len(idx) / n) * abs(bin_acc - bin_conf)
    return round(total, 4)


def brier_binary(probs: list[float], corrects: list[bool]) -> float:
    """Brier for a binary decision where `probs` is P(decision taken)."""
    if not probs:
        return 0.0
    return round(statistics.fmean((p - (1.0 if c else 0.0)) ** 2 for p, c in zip(probs, corrects)), 4)


def brier_multiclass(distributions: list[dict[str, float]], y_true: list[str]) -> float:
    """Multiclass Brier: sum over classes of (p_class - one_hot)^2, averaged."""
    if not distributions:
        return 0.0
    total = 0.0
    for dist, t in zip(distributions, y_true):
        total += sum((dist.get(c, 0.0) - (1.0 if c == t else 0.0)) ** 2 for c in DEPTS)
    return round(total / len(distributions), 4)


def run_selftest() -> int:
    # --- macro F1 known case ---
    f1 = macro_f1(["billing", "sales", "sales", "sales"],
                  ["billing", "billing", "sales", "sales"])
    # billing: tp1 fp1 fn1 -> p .5 r 1 f1 .6667 ; sales: tp2 fp0 fn1 -> f1 .8
    # present-classes macro = (.6667 + .8) / 2 = .7333
    assert abs(f1["macro_f1"] - 0.7333) < 1e-3, f1
    assert f1["per_class"]["sales"]["precision"] == 1.0

    # --- ECE: perfectly calibrated ---
    assert ece([0.8] * 5, [True, True, True, True, False]) == 0.0
    # --- ECE: overconfident and wrong ---
    assert ece([1.0] * 4, [False] * 4) == 1.0
    # --- ECE: mixed bins, hand-computed ---
    # bin [0.4,0.5): conf .45 acc 0   -> contributes .5 * |0-.45|
    # bin [0.9,1.0]: conf .95 acc 1.0 -> contributes .5 * 0.05
    got = ece([0.45, 0.95], [False, True], bins=10)
    want = 0.5 * 0.45 + 0.5 * 0.05
    assert abs(got - want) < 1e-6, (got, want)

    # --- Brier ---
    assert brier_binary([1.0, 0.0], [True, False]) == 0.0
    assert abs(brier_binary([0.7, 0.4], [True, False]) - (0.09 + 0.16) / 2) < 1e-9
    dist = [{"billing": 0.6, "technical": 0.4, "sales": 0.0, "account": 0.0}]
    assert abs(brier_multiclass(dist, ["billing"]) - (0.16 + 0.16)) < 1e-9

    print("selftest OK: macro-F1, ECE, and Brier math validated against known cases")
    return 0


# ---------------------------------------------------------------------------
# prediction extraction
# ---------------------------------------------------------------------------

def extract_predictions(result: dict) -> dict:
    """Map the runtime's answer schema (dict keyed by question name; see
    upstream README: result["answers"]["department"]) into eval records."""
    a = result["answers"]

    dep = a["department"]
    dep_dist = dep.get("probabilities") or {}
    dep_selected = dep.get("choice") or max(dep_dist, key=dep_dist.get)
    dep_conf = float(dep_dist.get(dep_selected, 0.0))

    urg = a["urgency"]
    urg_expected = float(urg.get("score", 0.0))
    urg_pred = min(2, max(0, round(urg_expected)))
    urg_probs = urg.get("probabilities") or {}
    urg_conf = float(urg_probs.get(str(urg_pred), 0.0))

    ref_p = float(a["refund"].get("noul", 0.0))
    return {
        "department": dep_selected, "department_dist": dep_dist, "department_conf": dep_conf,
        "urgency_pred": urg_pred, "urgency_conf": urg_conf,
        "refund_p": ref_p, "refund_pred": ref_p >= 0.5,
    }


def chip_name() -> str:
    try:
        return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                              capture_output=True, text=True, timeout=5).stdout.strip().replace(" ", "")
    except Exception:
        return platform.machine()


# ---------------------------------------------------------------------------
# main eval
# ---------------------------------------------------------------------------

def run_eval(path: Path, repeats: int, batch_size: int, strict: bool) -> int:
    import laya_mlx as laya

    dataset = json.loads(path.read_text())
    records = dataset["records"] if isinstance(dataset, dict) else dataset
    if not records:
        print(f"FAIL: no records in {path}")
        return 1

    qs = dataset.get("question_set") if isinstance(dataset, dict) else None
    if qs and qs != QUESTIONS:
        print("FAIL: golden set question_set does not match the eval runner's QUESTIONS. "
              "The eval would measure the wrong task; bump the dataset major version instead.")
        return 1

    print(f"loading checkpoint (batch_size={batch_size}) ...")
    t0 = time.perf_counter()
    agent = laya.load("aac6fef/laya-mlx", dtype="float16", batch_size=batch_size)
    print(f"loaded in {time.perf_counter() - t0:.1f}s; evaluating {len(records)} records x{repeats} pass(es)")

    # two full passes for determinism + latency samples
    all_passes = []
    latencies: list[float] = []
    for p in range(repeats):
        predictions = []
        for rec in records:
            t = time.perf_counter_ns()
            result = agent.predict(rec["text"], QUESTIONS)
            latencies.append((time.perf_counter_ns() - t) / 1e6)
            predictions.append(extract_predictions(result))
        all_passes.append(predictions)

    preds = all_passes[0]
    y_dep = [r["labels"]["department"] for r in records]
    y_urg = [r["labels"]["urgency"] for r in records]
    y_ref = [r["labels"]["refund"] for r in records]

    p_dep = [x["department"] for x in preds]
    p_urg = [x["urgency_pred"] for x in preds]
    p_ref = [x["refund_pred"] for x in preds]

    # determinism across passes
    deterministic = all(
        json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
        for x, y in zip(all_passes[0], all_passes[-1])
        for a, b in [(x, y)]
    ) if repeats > 1 else None

    dep_conf = [x["department_conf"] for x in preds]
    dep_ok = [p == t for p, t in zip(p_dep, y_dep)]
    urg_conf = [x["urgency_conf"] for x in preds if x["urgency_conf"] is not None]
    urg_ok = [p == t for p, t, x in zip(p_urg, y_urg, preds) if x["urgency_conf"] is not None]
    ref_p = [x["refund_p"] for x in preds]
    ref_ok = [p == t for p, t in zip(p_ref, y_ref)]

    acc = lambda ys, ps: round(statistics.fmean(1.0 if a == b else 0.0 for a, b in zip(ys, ps)), 4)

    report = {
        "schema": "adip.eval.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(path.relative_to(REPO_ROOT)),
        "n_records": len(records),
        "checkpoint": "aac6fef/laya-mlx",
        "dtype": "float16",
        "batch_size": batch_size,
        "passes": repeats,
        "environment": {"chip": chip_name(), "python": platform.python_version(),
                        "os": platform.platform()},
        "department": {
            **macro_f1(y_dep, p_dep),
            "accuracy": acc(y_dep, p_dep),
            "brier_multiclass": brier_multiclass([x["department_dist"] for x in preds], y_dep),
            "ece": ece(dep_conf, dep_ok),
            "confusion": confusion(y_dep, p_dep),
        },
        "urgency": {
            "accuracy": acc(y_urg, p_urg),
            "ece_on_predicted_level_mass": ece(urg_conf, urg_ok) if urg_conf else None,
        },
        "refund": {
            "accuracy": acc(y_ref, p_ref),
            "ece": ece(ref_p, ref_ok),
            "brier": brier_binary(ref_p, ref_ok),
        },
        "determinism_passes_identical": deterministic,
        "latency_ms": {
            "n": len(latencies),
            "p50": round(sorted(latencies)[len(latencies) // 2], 2),
            "mean": round(statistics.fmean(latencies), 2),
            "max": round(max(latencies), 2),
        },
        "gates": {},
    }

    if strict:
        report["gates"] = {
            "macro_f1_ge_0.85": report["department"]["macro_f1"] >= 0.85,
            "department_ece_lt_0.05": report["department"]["ece"] < 0.05,
            "refund_ece_lt_0.05": report["refund"]["ece"] < 0.05,
            "deterministic": deterministic is True,
            "latency_p95_lt_60ms": sorted(latencies)[int(0.95 * (len(latencies) - 1))] < 60,
        }
        report["gates_passed"] = all(report["gates"].values())

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = report["timestamp_utc"].replace(":", "").replace("-", "")[:15]
    out = RESULTS_DIR / f"eval-{chip_name()}-{stamp}.json"
    out.write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))
    print(f"\nreport: {out.relative_to(REPO_ROOT)}")
    if strict:
        status = "PASS" if report.get("gates_passed") else "FAIL"
        print(f"gates: {status} " + json.dumps(report["gates"]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", default="datasets/golden-set/golden-template.json")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--strict", action="store_true", help="apply blueprint section 9 gates")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()
    return run_eval(REPO_ROOT / args.file if not Path(args.file).is_absolute() else Path(args.file),
                    args.repeats, args.batch_size, args.strict)


if __name__ == "__main__":
    sys.exit(main())
