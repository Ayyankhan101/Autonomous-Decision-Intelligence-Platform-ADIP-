#!/usr/bin/env python3
"""Phase 2 model metrics (plan: evaluation metrics logged per model version).

Severity: accuracy + ECE (15 bins, same ece() as the Laya eval) on held-out.
Traffic: MAE, p10-p90 interval coverage, mean confidence (= 1 - width).
Anomaly: data-quality precision/recall/F1 at 0.5 + situational flag rate on clean rows.

Usage:
  uv run python evals/eval_ml.py --selftest
  uv run python evals/eval_ml.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval import ece  # noqa: E402

from jevcity.models.anomaly import AnomalyDetector  # noqa: E402
from jevcity.models.ml_data import load_dataset  # noqa: E402
from jevcity.models.severity import SeverityModel  # noqa: E402
from jevcity.models.traffic import TrafficModel  # noqa: E402

REPORT_PATH = REPO_ROOT / "evals/results/ml-phase2-v1.json"


def build_report() -> dict:
    _, held = load_dataset()
    severity = SeverityModel()
    traffic = TrafficModel()
    anomaly = AnomalyDetector()

    sev_conf: list[float] = []
    sev_ok: list[bool] = []
    for row in held:
        out = severity.predict(row["features"])
        sev_ok.append(out.prediction == row["severity"])
        sev_conf.append(out.confidence or 0.0)
    sev_acc = round(statistics.fmean(1.0 if ok else 0.0 for ok in sev_ok), 4)

    deltas = [float(traffic.predict(r["features"]).prediction) for r in held]
    tr_mae = round(statistics.fmean(
        abs(d - r["traffic_delta"]) for d, r in zip(deltas, held)
    ), 4)
    widths = []
    for row in held:
        out = traffic.predict(row["features"])
        widths.append(1.0 - (out.confidence or 0.0))
    coverage = round(statistics.fmean(
        1.0 if abs(d - r["traffic_delta"]) <= 0.1 else 0.0
        for d, r in zip(deltas, held)
    ), 4)

    from jevcity.schemas import ValidationFinding, ValidationResult, ValidationStatus
    tp = fp = fn = tn = 0
    clean_flags = []
    clean_n = 0
    for row in held:
        soft = [
            ValidationFinding(severity="soft", code=code, message=code)
            for code in row["validation"]["soft_codes"]
        ]
        validation = ValidationResult(
            event_id="evt-eval", incident_id="inc-eval",
            validation_status=ValidationStatus(row["validation"]["status"]),
            hard_errors=[],
            soft_warnings=soft,
        )
        out = anomaly.predict(row["features"], [], validation, [])
        predicted = out.data_quality_score >= 0.5
        actual = bool(row["dq_label"])
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif actual:
            fn += 1
        else:
            tn += 1
        if not actual:
            clean_n += 1
            clean_flags.append(1.0 if out.situational_anomaly else 0.0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0

    return {
        "schema": "jevcity.ml.v1",
        "dataset": "datasets/jevcity/ml/dataset.jsonl",
        "split": "i % 5 == 0 held-out",
        "models": {
            "severity": {
                "version": severity.version, "n": len(held),
                "accuracy": sev_acc, "ece": ece(sev_conf, sev_ok),
            },
            "traffic": {
                "version": traffic.version, "n": len(held),
                "mae": tr_mae, "interval_within_0.1": coverage,
                "mean_confidence": round(statistics.fmean(
                    1.0 - w for w in widths), 4),
            },
            "anomaly": {
                "version": anomaly.version, "n": len(held),
                "dq_precision": round(precision, 4),
                "dq_recall": round(recall, 4),
                "dq_f1": round(f1, 4),
                "situational_flag_rate_clean": round(
                    statistics.fmean(clean_flags) if clean_flags else 0.0, 4),
            },
        },
    }


def run_selftest() -> int:
    assert ece([0.5, 0.5], [True, False]) == 0.0
    assert abs(ece([0.9, 0.9], [True, True]) - 0.1) < 1e-9
    assert abs(ece([0.9] * 10, [True] * 10) - 0.1) < 1e-9
    report = build_report()
    assert report["schema"] == "jevcity.ml.v1"
    assert set(report["models"]) == {"severity", "traffic", "anomaly"}
    assert 0.0 <= report["models"]["severity"]["accuracy"] <= 1.0
    assert 0.0 <= report["models"]["severity"]["ece"] <= 1.0
    print("selftest OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return run_selftest()
    report = build_report()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"report: {REPORT_PATH.relative_to(REPO_ROOT)}")
    print(json.dumps(report["models"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
