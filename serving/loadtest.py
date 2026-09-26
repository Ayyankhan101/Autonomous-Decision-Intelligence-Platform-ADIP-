#!/usr/bin/env python3
"""Phase 0 end-to-end KPI measurement (blueprint section 10/11 exit criterion).

Drives DecisionService.in-process over the frozen golden tickets, N rounds,
then reports: pipeline P50 vs <= 150 ms and P95 vs <= 400 ms, per-stage P50,
route distribution for this run's decisions only, audit-replay verification
rate, and response-shape errors.

Exit 0 = both KPI targets met, every replay matched, no shape errors;
    1 = otherwise.

Usage:
  uv run python serving/loadtest.py --rounds 4
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adip.config import GOLDEN_SET_DEFAULT, KPI_P50_MS, KPI_P95_MS  # noqa: E402
from serving.pipeline import DecisionService, replay  # noqa: E402

# blueprint section 10: standard-mode pipeline target is <= 150 ms P50 and
# <= 400 ms P95. The pre-fix harness tested P95 against the P50 number, so the
# <= 400 ms gate was never evaluated by any artifact.
KPI_P50_TARGET_MS = KPI_P50_MS
KPI_P95_TARGET_MS = KPI_P95_MS

ROUTES = ("AUTO", "REVIEW", "ESCALATE")


def check_response(out: dict, errors: list[str]) -> None:
    """Response-shape checks. Explicit (not `assert`) so `python -O` cannot
    silently delete them."""
    rid = out.get("decision_id", "?")
    if out.get("route") not in ROUTES:
        errors.append(f"{rid}: route {out.get('route')!r} not in {ROUTES}")
    conf = out.get("decision", {}).get("department_conf", -1.0)
    if not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        errors.append(f"{rid}: department_conf {conf!r} outside [0, 1]")
    ref = out.get("decision", {}).get("refund_p_calibrated", -1.0)
    if not isinstance(ref, (int, float)) or not 0.0 <= ref <= 1.0:
        errors.append(f"{rid}: refund_p_calibrated {ref!r} outside [0, 1]")
    if not out.get("explanation"):
        errors.append(f"{rid}: empty explanation")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=4, help="passes over the 50 tickets")
    ap.add_argument("--audit", default=str(Path(__file__).resolve().parent / "audit.db"))
    ap.add_argument("--dataset", default=GOLDEN_SET_DEFAULT)
    args = ap.parse_args()
    if args.rounds < 1:
        ap.error(f"--rounds must be >= 1, got {args.rounds}")

    ds = Path(args.dataset)
    if not ds.is_absolute():
        # relative paths resolve against the repo root, not the caller's cwd
        ds = Path(__file__).resolve().parent.parent / ds
    golden = json.loads(ds.read_text())["records"]
    texts = [r["text"] for r in golden]

    svc = DecisionService(audit_path=args.audit)
    ids: list[str] = []
    shape_errors: list[str] = []
    for _ in range(args.rounds):
        for t in texts:
            out = svc.decide(t)
            ids.append(out["decision_id"])
            check_response(out, shape_errors)

    s = svc.summary()
    if shape_errors:
        for e in shape_errors[:20]:
            print(f"SHAPE: {e}", file=sys.stderr)

    # Route distribution + replay verification, scoped to THIS run's ids: the
    # audit db persists across runs, so reading the whole table folded previous
    # runs' rows into this report's route_mix / audit_rows / replay sample.
    idset = set(ids)
    placeholders = ",".join("?" * len(idset))
    conn = sqlite3.connect(args.audit)
    try:
        audit_rows_total = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        rows = conn.execute(
            f"SELECT decision_id, route, text_redacted, decision_json FROM decisions "
            f"WHERE decision_id IN ({placeholders})", tuple(idset)).fetchall()
    finally:
        conn.close()

    route_mix = Counter(r[1] for r in rows)
    replay_sample = rows[:10] + rows[-10:] if len(rows) > 20 else rows
    replay_ok = 0
    for did, *_ in replay_sample:
        r = replay(did, audit_path=args.audit)
        replay_ok += 1 if r["matches"] else 0
        if not r["matches"]:
            print(f"REPLAY MISMATCH: {did}", file=sys.stderr)

    p50, p95 = s["pipeline_p50_ms"], s["pipeline_p95_ms"]
    # explicit `is not None`: a rounded-to-zero p95 is a pass, not a missing
    # sample (the old `(x or 1e9) <= target` treated 0.0 as absent)
    kpi_p50_pass = p50 is not None and p50 <= KPI_P50_TARGET_MS
    kpi_p95_pass = p95 is not None and p95 <= KPI_P95_TARGET_MS
    replay_rate = round(replay_ok / max(len(replay_sample), 1), 4)

    result = {
        "schema": "adip.loadtest.v2",
        "dataset": str(Path(args.dataset).name),
        "rounds": args.rounds,
        "n_calls": len(ids),
        "pipeline_p50_ms": p50,
        "pipeline_p95_ms": p95,
        "kpi_targets_ms": {"p50": KPI_P50_TARGET_MS, "p95": KPI_P95_TARGET_MS},
        "kpi_p50_pass": kpi_p50_pass,
        "kpi_p95_pass": kpi_p95_pass,
        "kpi_pass": kpi_p50_pass and kpi_p95_pass,
        "stage_p50_ms": s["stage_p50_ms"],
        "audit_rows_this_run": len(rows),
        "audit_rows_total": audit_rows_total,
        "route_mix": dict(route_mix),
        "replay_checked": len(replay_sample),
        "replay_verified": replay_ok,
        "replay_rate": replay_rate,
        "shape_errors": len(shape_errors),
    }
    print(json.dumps(result, indent=2))
    out = Path(__file__).resolve().parent / "results" / f"loadtest-{args.rounds}r.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"saved: {out}")
    ok = result["kpi_pass"] and replay_rate == 1.0 and not shape_errors and len(rows) == len(idset)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
