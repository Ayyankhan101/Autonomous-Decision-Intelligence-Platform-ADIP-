#!/usr/bin/env python3
"""Deterministic fixture generator (plan Phase 2 'Added for Laya').

Captures the LayaState the engine actually built per decision (build_state
monkeypatched at the engine module — imported by name at engine.py:41) and freezes
the baseline proposer's answers (mock adapter LayaBlock) as expected labels."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import jevcity.decision_engine.engine as engine_mod  # noqa: E402
from jevcity.api.app import build_engine  # noqa: E402
from jevcity.schemas import (  # noqa: E402
    InjectionMode,
    IncidentType,
    ResourceType,
    SeverityHint,
    Zone,
)

SESSIONS = [(42 + i, 7 + i) for i in range(7)]
HINTS = [SeverityHint.MINOR, SeverityHint.MODERATE, SeverityHint.SEVERE]
TYPES = list(IncidentType)
ZONES = list(Zone)
BAD_MODES = [InjectionMode.MISSING_FIELDS, InjectionMode.CONFLICTING_REPORTS]


def generate() -> list[dict]:
    captured: dict[str, dict] = {}
    original = engine_mod.build_state

    def capture(**kwargs):
        state = original(**kwargs)
        captured[kwargs["incident_id"]] = state.model_dump(mode="json")
        return state

    engine_mod.build_state = capture
    rows: list[dict] = []
    try:
        for session_seed, scenario_seed in SESSIONS:
            engine = build_engine()
            engine.simulation.start(session_seed, scenario_seed)
            if session_seed >= SESSIONS[5][0]:
                for resource in engine.simulation.pool.all():
                    if resource.type is ResourceType.AMBULANCE:
                        engine.simulation.pool.take_offline(resource.resource_id)
            plan: list[tuple] = []
            for i, hint in enumerate(HINTS):
                for j, itype in enumerate(TYPES):
                    zone = ZONES[(i + j + session_seed) % len(ZONES)]
                    plan.append(("inject", itype, zone, hint, (i + j) % 3 == 0))
            plan.append(("bad", None, None, None, False))
            plan.append(("bad", None, None, None, False))
            for kind, itype, zone, hint, multi in plan:
                if kind == "bad":
                    mode = BAD_MODES[len(rows) % len(BAD_MODES)]
                    engine.simulation.inject_bad_data(mode)
                else:
                    engine.simulation.inject_incident(
                        itype, zone, hint, multi_report=multi
                    )
            for record in engine.process_pending():
                state = captured.get(record.incident_id)
                laya = record.laya
                if state is None or laya is None or laya.suggested_priority is None:
                    continue
                if laya.recommended_resource_type is None:
                    continue
                rows.append({
                    "state": state,
                    "expected": {
                        "priority": laya.suggested_priority.value,
                        "needs_human_review": bool(laya.suggested_needs_human_review),
                        "recommended_resource_type": laya.recommended_resource_type.value,
                    },
                })
    finally:
        engine_mod.build_state = original
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO_ROOT / "fixtures/jevcity_decisions.jsonl"))
    args = ap.parse_args()
    rows = generate()
    if len(rows) < 50:
        print(f"FAIL: only {len(rows)} fixtures (<50)", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    print(f"{len(rows)} fixtures -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
