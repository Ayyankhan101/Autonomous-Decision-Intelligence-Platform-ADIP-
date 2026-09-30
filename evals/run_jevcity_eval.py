#!/usr/bin/env python3
"""JevCity fixture eval for the laya-typed-decisions checkpoint (plan Phase 2).

Gates (ERRATA C4, frozen): accuracy >= 0.70, ECE <= 0.15.
accuracy = mean of the three per-question accuracies over fixtures.
ECE (15 bins) pooled over all three answers: confidence = answer_confidence
(derived top-of-distribution, ERRATA C2), paired with that answer's correctness.

Usage:
  uv run python evals/run_jevcity_eval.py --selftest
  uv run python evals/run_jevcity_eval.py --file fixtures/jevcity_decisions.jsonl --strict --repeats 2
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval import ece  # noqa: E402

from jevcity.decision_engine.laya_adapter.normalize import (  # noqa: E402
    CHECKPOINT,
    normalize,
    to_raw,
)
from jevcity.decision_engine.laya_adapter.questions import QUESTIONS  # noqa: E402
from jevcity.decision_engine.laya_adapter.state_text import render_state  # noqa: E402
from jevcity.schemas import LayaRequest, LayaState  # noqa: E402

ACC_GATE = 0.70
ECE_GATE = 0.15
DTYPE = "float16"
QUESTION_KEYS = ("priority", "needs_human_review", "recommended_resource_type")


def score_answers(normalized: dict, expected: dict) -> dict[str, tuple[float, bool]]:
    out: dict[str, tuple[float, bool]] = {}
    priority = normalized.get("priority")
    if priority is None:
        out["priority"] = (0.0, False)
    else:
        out["priority"] = (
            priority.answer_confidence,
            priority.choice == expected["priority"],
        )
    review = normalized.get("needs_human_review")
    if review is None:
        out["needs_human_review"] = (0.0, False)
    else:
        predicted = review.noul >= 0.5
        out["needs_human_review"] = (
            review.answer_confidence,
            predicted == bool(expected["needs_human_review"]),
        )
    resource = normalized.get("recommended_resource_type")
    if resource is None:
        out["recommended_resource_type"] = (0.0, False)
    else:
        out["recommended_resource_type"] = (
            resource.answer_confidence,
            resource.choice == expected["recommended_resource_type"],
        )
    return out


def aggregate(per_question: dict) -> dict:
    accs = [q["accuracy"] for q in per_question.values()]
    eces = [q["ece"] for q in per_question.values()]
    return {
        "accuracy": round(statistics.fmean(accs), 4),
        "ece": round(statistics.fmean(eces), 4),
    }


def gates_passed(overall: dict) -> bool:
    return overall["accuracy"] >= ACC_GATE and overall["ece"] <= ECE_GATE


def run_eval(path: Path, repeats: int, batch_size: int, strict: bool) -> int:
    import laya_mlx as laya

    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        print(f"FAIL: no fixtures in {path}")
        return 1
    for row in rows:
        LayaState.model_validate(row["state"])

    print(f"loading checkpoint (batch_size={batch_size}) ...", file=sys.stderr)
    agent = laya.load(CHECKPOINT, dtype=DTYPE, batch_size=batch_size)
    questions = {k: v.model_dump(mode="json") for k, v in QUESTIONS.items()}

    for i in range(min(2, len(rows))):
        agent.predict(render_state(LayaState.model_validate(rows[i]["state"])),
                      questions)

    all_passes: list[list[dict]] = []
    latencies: list[float] = []
    for _ in range(repeats):
        predictions = []
        for row in rows:
            state = LayaState.model_validate(row["state"])
            t0 = time.perf_counter_ns()
            result = agent.predict(render_state(state), questions)
            latencies.append((time.perf_counter_ns() - t0) / 1e6)
            raw = to_raw(result)
            if raw is None:
                predictions.append(None)
                continue
            request = LayaRequest(state=state, questions=QUESTIONS)
            normalized = normalize(
                request, raw,
                state_hash="sha256:fixture",
                questions_hash="sha256:fixture",
                latency_ms=latencies[-1],
            )
            predictions.append(
                score_answers(normalized.answers, row["expected"])
                if normalized.status.value == "ok" else None
            )
        all_passes.append(predictions)

    deterministic = (
        json.dumps(all_passes[0], sort_keys=True)
        == json.dumps(all_passes[-1], sort_keys=True)
    ) if repeats > 1 else None

    first = all_passes[0]
    per_question: dict[str, dict] = {}
    pooled_conf: list[float] = []
    pooled_ok: list[bool] = []
    for key in QUESTION_KEYS:
        pairs = [p[key] for p in first if p is not None]
        missing = sum(1 for p in first if p is None)
        conf = [c for c, _ in pairs] + [0.0] * missing
        ok = [o for _, o in pairs] + [False] * missing
        per_question[key] = {
            "accuracy": round(statistics.fmean(1.0 if o else 0.0 for o in ok), 4),
            "ece": ece(conf, ok),
            "n": len(ok),
        }
        pooled_conf.extend(conf)
        pooled_ok.extend(ok)
    overall = {
        "accuracy": round(
            statistics.fmean(q["accuracy"] for q in per_question.values()), 4),
        "ece": ece(pooled_conf, pooled_ok),
    }
    passed = gates_passed(overall) and (deterministic is not False)
    report = {
        "schema": "jevcity.eval.v1",
        "file": str(path.relative_to(REPO_ROOT)),
        "checkpoint": CHECKPOINT,
        "n": len(rows),
        "repeats": repeats,
        "accuracy": overall["accuracy"],
        "ece": overall["ece"],
        "per_question": per_question,
        "determinism": deterministic,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 3),
            "max": round(max(latencies), 3),
        },
        "gates": {"accuracy": ACC_GATE, "ece": ECE_GATE},
        "gates_passed": passed,
    }
    out = REPO_ROOT / "evals/results" / f"eval-jevcity-{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"report: {out.relative_to(REPO_ROOT)}")
    print(json.dumps({k: report[k] for k in
                      ("accuracy", "ece", "gates_passed", "n")}, indent=2))
    if strict and not passed:
        return 1
    return 0


def run_selftest() -> int:
    assert to_raw({"answers": {}}) is None
    sample = {
        "answers": {
            "priority": {"choice": "HIGH", "probabilities": {"HIGH": 0.7, "LOW": 0.3}},
            "needs_human_review": {"noul": 0.8},
            "recommended_resource_type": {
                "choice": "ambulance",
                "probabilities": {"ambulance": 0.9, "fire_truck": 0.1},
            },
        }
    }
    raw = to_raw(sample)
    assert raw is not None
    assert raw["priority"]["choice"] == "HIGH"
    assert abs(raw["needs_human_review"]["answer_confidence"] - 0.8) < 1e-9
    expected = {"priority": "HIGH", "needs_human_review": True,
                "recommended_resource_type": "ambulance"}
    state_dict = {
        "incident_id": "inc-1", "incident_type": "accident", "zone": "north",
        "simulated_time": "2026-09-27T10:00:01Z", "data_quality_score": 0.1,
        "available_ambulances": 2, "active_competing_incidents": 0,
    }
    request = LayaRequest(state=LayaState.model_validate(state_dict), questions=QUESTIONS)
    normalized = normalize(request, raw, state_hash="sha256:x",
                           questions_hash="sha256:y", latency_ms=1.0)
    scores = score_answers(normalized.answers, expected)
    assert scores["priority"][1] is True
    assert scores["needs_human_review"][1] is True
    perfect = {"priority": {"accuracy": 0.8, "ece": 0.1},
               "needs_human_review": {"accuracy": 0.7, "ece": 0.2},
               "recommended_resource_type": {"accuracy": 0.9, "ece": 0.1}}
    overall = aggregate(perfect)
    assert overall["accuracy"] == 0.8
    assert gates_passed(overall) is True
    assert gates_passed({"accuracy": 0.69, "ece": 0.1}) is False
    assert gates_passed({"accuracy": 0.9, "ece": 0.16}) is False
    assert ACC_GATE == 0.70 and ECE_GATE == 0.15
    print("selftest OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="fixtures/jevcity_decisions.jsonl")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return run_selftest()
    if args.strict and args.repeats < 2:
        ap.error("--strict requires --repeats >= 2")
    target = Path(args.file)
    if not target.is_absolute():
        target = REPO_ROOT / target
    return run_eval(target, args.repeats, args.batch_size, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
