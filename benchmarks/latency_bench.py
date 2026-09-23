#!/usr/bin/env python3
"""ADIP latency benchmark harness for laya-mlx on local Apple Silicon.

Mirrors the methodology of the laya-mlx repo's checked-in BENCHMARKS.md:
  * fresh process per configuration (batch sizes run as separate invocations),
  * warmup iterations excluded, timed iterations all recorded,
  * end-to-end wall-clock timing boundary: prompt construction + tokenization +
    tensor construction + model execution + calibration + result formatting.
    Model loading and checkpoint download are excluded.
  * every timing sample is stored in the results JSON.

Usage:
  python3 benchmarks/latency_bench.py --batch-size 1  --repeats 50
  python3 benchmarks/latency_bench.py --batch-size 5  --repeats 50
  python3 benchmarks/latency_bench.py --batch-size 10 --repeats 50
  python3 benchmarks/latency_bench.py --batch-size 1  --full-context
  python3 benchmarks/latency_bench.py --selftest          # no model download

Results are written to benchmarks/results/latency-<host>-<timestamp>.json
with the full environment record and every raw timing sample.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"

CHECKPOINT = "aac6fef/laya-mlx"

STATE_SHORT = "I was billed twice. Please refund the duplicate charge from last Tuesday."
STATE_FULL = (
    "Ticket 48213 - customer reports a duplicate charge on invoice INV-2026-0117. "
    "The customer was billed twice for the annual subscription renewal on March 3rd "
    "and March 4th. They have already checked their bank statement and confirmed two "
    "separate charges of $249.00 each. They contacted support twice before; the first "
    "agent promised a callback within 24 hours but nothing happened. The customer is "
    "frustrated, mentions they are considering a chargeback, and asks for the refund "
    "to be processed today. Account status: premium subscriber since 2021, no prior "
    "refund requests, payment method Visa ending 4242. The billing system shows two "
    "successful capture events 26 hours apart referencing the same order id. "
) * 4  # padded to ~512 tokens at load; the runtime truncates at its context limit

# Question set mirrors evals/run_eval.py QUESTIONS and the golden set's
# question_set. Latency is insensitive to criteria wording, but the payloads
# must stay in sync so results stay comparable across harnesses; if you change
# one, change all three (eval runner, golden set, this file).
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

N_QUESTIONS = len(QUESTIONS)  # questions per predict() call


# --------------------------------------------------------------------------
# stats helpers (pure python, covered by --selftest)
# --------------------------------------------------------------------------

def percentile(sorted_samples: list[float], pct: float) -> float:
    """Linear-interpolated percentile on a pre-sorted list."""
    if not sorted_samples:
        raise ValueError("empty sample list")
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    rank = (pct / 100.0) * (len(sorted_samples) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_samples) - 1)
    frac = rank - lo
    return sorted_samples[lo] * (1 - frac) + sorted_samples[hi] * frac


def summarize(samples_ms: list[float], questions_per_call: int) -> dict:
    s = sorted(samples_ms)
    p50 = percentile(s, 50)
    return {
        "n": len(s),
        "min_ms": round(s[0], 3),
        "p50_ms": round(p50, 3),
        "p95_ms": round(percentile(s, 95), 3),
        "mean_ms": round(statistics.fmean(s), 3),
        "max_ms": round(s[-1], 3),
        "questions_per_call": questions_per_call,
        "q_per_s_at_p50": round(questions_per_call * 1000.0 / p50, 2),
    }


def run_selftest() -> int:
    """Validate the harness math without downloading any model."""
    cases = [
        ([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0]),
        ([5.0], [5.0]),
        ([10.0, 20.0, 30.0], [10.0, 15.0, 20.0, 25.0, 30.0]),
    ]
    for raw, expected_order in cases:
        got = [percentile(sorted(raw), p) for p in (0, 25, 50, 75, 100)]
        want = [percentile(expected_order, p) for p in (0, 25, 50, 75, 100)]
        assert got == want, f"percentile mismatch: {got} != {want}"
    # sanity: known small case
    assert percentile([1, 2, 3, 4], 50) == 2.5
    summary = summarize([17.0, 17.5, 18.0, 22.0, 30.0], 3)
    assert summary["p50_ms"] == 18.0 and summary["n"] == 5
    print("selftest OK: percentile + summary math validated")
    return 0


# --------------------------------------------------------------------------
# environment record
# --------------------------------------------------------------------------

def mac_env() -> dict:
    env = {
        "machine": platform.machine(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "os": platform.platform(),
    }
    try:
        env["chip"] = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        env["chip"] = "unknown"
    try:
        env["ram_gb"] = round(
            int(subprocess.run(["sysctl", "-n", "hw.memsize"],
                               capture_output=True, text=True, timeout=5).stdout)
            / 1024**3
        )
    except Exception:
        env["ram_gb"] = None
    return env


# --------------------------------------------------------------------------
# benchmark run (single batch size, fresh process)
# --------------------------------------------------------------------------

def bench(batch_size: int, repeats: int, warmup: int, full_context: bool,
          dtype: str) -> dict:
    import resource  # apple/unix only, fine for this harness

    import laya_mlx as laya  # deferred so --selftest needs no mlx

    t_load0 = time.perf_counter()
    agent = laya.load(CHECKPOINT, dtype=dtype, batch_size=batch_size)
    load_s = time.perf_counter() - t_load0

    state = STATE_FULL if full_context else STATE_SHORT
    state_chars = len(state)

    # warmup (excluded from samples)
    for _ in range(warmup):
        agent.predict(state, QUESTIONS)

    samples_ms: list[float] = []
    last_result = None
    for _ in range(repeats):
        t0 = time.perf_counter_ns()
        last_result = agent.predict(state, QUESTIONS)
        t1 = time.perf_counter_ns()
        samples_ms.append((t1 - t0) / 1e6)

    # determinism check: rerun once, hash the JSON, compare with last timed run
    det_result = agent.predict(state, QUESTIONS)
    det_hash = hashlib.sha256(
        json.dumps(det_result["answers"], sort_keys=True).encode()
    ).hexdigest()
    last_hash = hashlib.sha256(
        json.dumps(last_result["answers"], sort_keys=True).encode()
    ).hexdigest()
    deterministic = det_hash == last_hash

    # ru_maxrss is bytes on macOS, KiB on Linux; normalize to MiB
    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == "darwin" else 1024)

    record = {
        "schema": "adip.latency.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint": CHECKPOINT,
        "dtype": dtype,
        "config": {
            "batch_size": batch_size,
            "repeats": repeats,
            "warmup": warmup,
            "full_context": full_context,
            "state_chars": state_chars,
            "questions_per_call": N_QUESTIONS,
            "timing_boundary": "end-to-end predict() wall clock; model load excluded",
        },
        "environment": mac_env(),
        "model_load_seconds": round(load_s, 2),
        "determinism": {
            "runs_compared": 2,
            "identical_answers_json": deterministic,
        },
        "peak_process_rss_mib": round(peak_rss_mb, 1),
        "summary": summarize(samples_ms, N_QUESTIONS),
        "samples_ms": [round(x, 4) for x in samples_ms],
    }
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--repeats", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--full-context", action="store_true",
                    help="use a ~512-token state instead of a short one")
    ap.add_argument("--dtype", default="float16", choices=["float16", "float32"])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    record = bench(args.batch_size, args.repeats, args.warmup,
                   args.full_context, args.dtype)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    host = record["environment"]["chip"].replace(" ", "").replace("/", "-")
    stamp = record["timestamp_utc"].replace(":", "").replace("-", "")[:15]
    suffix = "fullctx" if args.full_context else f"b{args.batch_size}"
    out = RESULTS_DIR / f"latency-{host}-{suffix}-{stamp}.json"
    out.write_text(json.dumps(record, indent=2))
    record["results_file"] = str(out.relative_to(REPO_ROOT))

    print(json.dumps({k: v for k, v in record.items() if k != "samples_ms"},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
