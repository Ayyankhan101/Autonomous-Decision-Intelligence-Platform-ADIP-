#!/usr/bin/env python3
"""JevCity event-pipeline load/latency benchmark (plan Phase 6).

Measures end-to-end per-event decision latency through the real pipeline:
inject -> correlate -> feature build -> ML triad -> Laya advisory -> guardrail
-> allocation -> audit append. Timing boundary is wall clock around
``inject_incident() + process_pending()``; model loading and engine construction
are excluded (one warmup pass runs first).

Budgets (plan §5 demo / §6 CPU targets, ms):
  * demo budget: p95 < 250 ms
  * cpu budget:  p95 < 750 ms

Exit code 1 when the selected budget is exceeded (never green-wash).

Usage:
  uv run python benchmarks/jevcity_pipeline_bench.py --events 50
  uv run python benchmarks/jevcity_pipeline_bench.py --events 20 --laya live
  uv run python benchmarks/jevcity_pipeline_bench.py --budget demo --events 50

Results are written to benchmarks/results/jevcity-pipeline-<host>-<timestamp>.json
with environment record, budget verdicts, and every raw timing sample.
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from adip.stats import percentile  # noqa: E402
from jevcity.api.app import build_engine  # noqa: E402
from jevcity.schemas import IncidentType, LayaMode, SeverityHint, Zone  # noqa: E402

RESULTS_DIR = REPO_ROOT / "benchmarks" / "results"

BUDGETS_MS = {"demo": 250.0, "cpu": 750.0}

_CYCLE = [
    (IncidentType.ACCIDENT, Zone.NORTH, SeverityHint.SEVERE),
    (IncidentType.FIRE, Zone.SOUTH, SeverityHint.MODERATE),
    (IncidentType.FLOOD, Zone.EAST, SeverityHint.SEVERE),
    (IncidentType.TRAFFIC_SPIKE, Zone.WEST, SeverityHint.MINOR),
    (IncidentType.ACCIDENT, Zone.CENTRAL, SeverityHint.MODERATE),
    (IncidentType.FIRE, Zone.NORTH, SeverityHint.SEVERE),
]


def summarize(samples_ms: list[float]) -> dict:
    s = sorted(samples_ms)
    return {
        "n": len(s),
        "min_ms": round(s[0], 3),
        "p50_ms": round(percentile(s, 50), 3),
        "p95_ms": round(percentile(s, 95), 3),
        "mean_ms": round(statistics.fmean(s), 3),
        "max_ms": round(s[-1], 3),
    }


def run(events: int, warmup: int, laya: str) -> list[float]:
    engine = build_engine(mode=LayaMode(laya))
    samples: list[float] = []

    def one(i: int) -> None:
        itype, zone, sev = _CYCLE[i % len(_CYCLE)]
        start = time.perf_counter()
        engine.simulation.inject_incident(itype, zone, sev)
        engine.process_pending()
        samples.append((time.perf_counter() - start) * 1000.0)

    for i in range(warmup):
        one(i)
    samples.clear()
    for i in range(events):
        one(i)
    engine.audit.close()
    return samples


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--laya", choices=["mock", "cache", "live"], default="mock")
    ap.add_argument("--budget", choices=sorted(BUDGETS_MS), default="demo")
    args = ap.parse_args()

    samples = run(args.events, args.warmup, args.laya)
    stats = summarize(samples)
    budget_ms = BUDGETS_MS[args.budget]
    passed = stats["p95_ms"] <= budget_ms

    record = {
        "benchmark": "jevcity-event-pipeline",
        "host": socket.gethostname(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "laya_mode": args.laya,
        "events": args.events,
        "warmup": args.warmup,
        "budget": {"name": args.budget, "p95_ms": budget_ms, "passed": passed},
        "stats": stats,
        "samples_ms": [round(s, 3) for s in samples],
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = RESULTS_DIR / f"jevcity-pipeline-{platform.machine()}-{stamp}.json"
    out.write_text(json.dumps(record, indent=2))
    print(json.dumps({k: v for k, v in record.items() if k != "samples_ms"}, indent=2))
    print(f"results: {out}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
