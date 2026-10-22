#!/usr/bin/env python3
"""Deterministic fixture generator (plan Phase 2 'Added for Laya').

Captures the LayaState the engine actually built per decision (build_state
monkeypatched at the engine module — imported by name at engine.py:41) and
freezes policy-only ground truth as expected labels (ERRATA C4 re-anchor):

- priority: record.priority — governed final (model signals only, never Laya).
- needs_human_review: policy-only hold routing — HOLD_FOR_HUMAN caused by a
  non-Laya hold rule (data quality / low confidence), or MODEL_DEGRADED.
  Holds triggered solely by the mock proposer's advisory (R-LAYA-*) do not
  count: that would grade the checkpoint against the stub's opinion.
- recommended_resource_type: FALLBACK_RESOURCE[incident_type][0] — the
  type-semantic mapping the allocator uses when no advisory is present.
  Mock-proposer recommendations dominate allocation, so the allocated unit
  type is not a valid gold label either.

Each planned incident uses a unique source_id: one burst from a single stream
would trip the rate-limit trust penalty and R-TRUST-down-weight every row,
making CRITICAL unreachable under invariant 5."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import jevcity.decision_engine.engine as engine_mod  # noqa: E402
from jevcity.api.app import build_engine  # noqa: E402
from jevcity.decision_engine.guardrail.allocate import (  # noqa: E402
    FALLBACK_RESOURCE,
)
from jevcity.decision_engine.guardrail.policy import (  # noqa: E402
    R_LOW_CONF,
    R_MODEL_FAILURE,
    R_DQ_HOLD,
)
from jevcity.schemas import (  # noqa: E402
    DecisionState,
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
POLICY_HOLD_RULES = frozenset({R_DQ_HOLD, R_LOW_CONF, R_MODEL_FAILURE})


def _policy_review(record) -> bool:
    if record.state is DecisionState.MODEL_DEGRADED:
        return True
    if record.state is not DecisionState.HOLD_FOR_HUMAN:
        return False
    return any(r in POLICY_HOLD_RULES for r in record.matched_rules)


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
            engine = build_engine(audit_path=":memory:")
            engine.simulation.start(session_seed, scenario_seed)
            if session_seed >= SESSIONS[5][0]:
                for resource in engine.simulation.pool.all():
                    if resource.type is ResourceType.AMBULANCE:
                        engine.simulation.pool.take_offline(resource.resource_id)
            plan: list[tuple] = []
            k = 0
            for i, hint in enumerate(HINTS):
                for j, itype in enumerate(TYPES):
                    zone = ZONES[(i + j + session_seed) % len(ZONES)]
                    plan.append(("inject", itype, zone, hint, (i + j) % 3 == 0, k))
                    k += 1
            plan.append(("bad", None, None, None, False, None))
            plan.append(("bad", None, None, None, False, None))
            for kind, itype, zone, hint, multi, idx in plan:
                if kind == "bad":
                    mode = BAD_MODES[len(rows) % len(BAD_MODES)]
                    engine.simulation.inject_bad_data(mode)
                else:
                    engine.simulation.inject_incident(
                        itype, zone, hint, multi_report=multi,
                        source_id=f"stream-{idx:03d}",
                    )
            for record in engine.process_pending():
                state = captured.get(record.incident_id)
                if state is None or record.state is DecisionState.REJECTED_INPUT:
                    continue
                itype = IncidentType(state["incident_type"])
                rows.append({
                    "state": state,
                    "expected": {
                        "priority": record.priority.value,
                        "needs_human_review": _policy_review(record),
                        "recommended_resource_type": (
                            FALLBACK_RESOURCE[itype][0].value
                        ),
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
