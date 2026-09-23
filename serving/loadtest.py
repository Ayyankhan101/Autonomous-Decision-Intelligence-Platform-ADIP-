#!/usr/bin/env python3
"""Phase 0 end-to-end KPI measurement (blueprint section 10/11 exit criterion).

Drives DecisionService.in-process over the 50 frozen golden tickets, N rounds,
then reports: pipeline P50/P95 vs the <= 150 ms KPI, per-stage P50, route
distribution, audit-replay verification rate, and JSON validity of the output.

Usage:
  .venv-bench/bin/python serving/loadtest.py --rounds 4
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from serving.pipeline import DecisionService, replay  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=4, help="passes over the 50 tickets")
    ap.add_argument("--audit", default=str(Path(__file__).resolve().parent / "audit.db"))
    args = ap.parse_args()

    golden = json.loads(
        (Path(__file__).resolve().parent.parent / "datasets/golden-set/golden-v1.0.json").read_text()
    )["records"]
    texts = [r["text"] for r in golden]

    svc = DecisionService(audit_path=args.audit)
    ids = []
    for _ in range(args.rounds):
        for t in texts:
            out = svc.decide(t)
            ids.append(out["decision_id"])
            # response-shape sanity on every call
            assert out["route"] in ("AUTO", "REVIEW", "ESCALATE"), out["route"]
            assert 0.0 <= out["decision"]["department_conf"] <= 1.0
            assert 0.0 <= out["decision"]["refund_p_calibrated"] <= 1.0
            assert out["explanation"], "empty explanation"

    s = svc.summary()

    # route distribution + replay verification from the audit log (source of truth)
    import sqlite3
    conn = sqlite3.connect(args.audit)
    rows = conn.execute("SELECT decision_id, route, text_redacted, decision_json FROM decisions").fetchall()
    route_mix = Counter(r[1] for r in rows)
    replay_sample = rows[:10] + rows[-10:] if len(rows) > 20 else rows
    replay_ok = 0
    for did, *_ in replay_sample:
        r = replay(did, audit_path=args.audit)
        replay_ok += 1 if r["matches"] else 0
        if not r["matches"]:
            print(f"REPLAY MISMATCH: {did}", file=sys.stderr)

    result = {
        "schema": "adip.loadtest.v1",
        "rounds": args.rounds,
        "n_calls": svc.summary()["n"],
        "pipeline_p50_ms": s["pipeline_p50_ms"],
        "pipeline_p95_ms": s["pipeline_p95_ms"],
        "kpi_target_ms": 150,
        "kpi_pass": (s["pipeline_p95_ms"] or 1e9) <= 150,
        "stage_p50_ms": s["stage_p50_ms"],
        "audit_rows": len(rows),
        "route_mix": dict(route_mix),
        "replay_checked": len(replay_sample),
        "replay_verified": replay_ok,
        "replay_rate": round(replay_ok / max(len(replay_sample), 1), 4),
    }
    print(json.dumps(result, indent=2))
    out = Path(__file__).resolve().parent / "results" / f"loadtest-{args.rounds}r.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"saved: {out}")
    return 0 if result["kpi_pass"] and result["replay_rate"] == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
