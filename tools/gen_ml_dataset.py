#!/usr/bin/env python3
"""Deterministic Phase 2 dataset generator: seed-sweep simulator sessions -> labels.

Severity label = documented mapping of the primary report's severity hint
(minor->LOW, moderate->MEDIUM, severe->HIGH; severe with >=2 injuries -> CRITICAL).
Traffic label = approved heuristic `traffic_delta` (sign-off item 3 / ERRATA C5).
dq_label = 1 iff any report carries quality_hints.injection_mode (bad-data modes).
Split rule: row index % 5 == 0 -> held-out (shared by loader, eval)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from jevcity.decision_engine.engine import JevCityEngine  # noqa: E402
from jevcity.models.traffic import traffic_delta  # noqa: E402
from jevcity.schemas import (  # noqa: E402
    AnomalyOutput,
    IncidentType,
    InjectionMode,
    ModelOutput,
    ModelStatus,
    SeverityHint,
    Zone,
)
from jevcity.simulation.seeds import SeedConfig  # noqa: E402
from jevcity.simulation.state import SimulationState  # noqa: E402

SESSIONS = [(42 + i, 7 + i) for i in range(25)]
HINTS = [SeverityHint.MINOR, SeverityHint.MODERATE, SeverityHint.SEVERE]
TYPES = list(IncidentType)
ZONES = list(Zone)
BAD_MODES = list(InjectionMode)


class _StubSeverity:
    name = "stub"
    version = "0"

    def predict(self, features: dict) -> ModelOutput:
        return ModelOutput(status=ModelStatus.OK, model_name=self.name,
                           model_version=self.version, prediction="LOW",
                           confidence=0.5, latency_ms=0.0)


class _StubTraffic(_StubSeverity):
    def predict(self, features: dict) -> ModelOutput:
        return ModelOutput(status=ModelStatus.OK, model_name=self.name,
                           model_version=self.version,
                           prediction=f"{traffic_delta(features):.2f}",
                           confidence=0.5, latency_ms=0.0)


class _ProbeAnomaly:
    name = "probe"
    version = "0"

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def predict(self, features, reports, validation, contradictions) -> AnomalyOutput:
        hint = features.get("severity_hint") or "moderate"
        injuries = features.get("injuries_reported") or 0
        if hint == "severe" and injuries >= 2:
            label = "CRITICAL"
        else:
            label = {"minor": "LOW", "moderate": "MEDIUM", "severe": "HIGH"}[hint]
        self.rows.append({
            "features": features,
            "validation": {
                "hard": len(validation.hard_errors),
                "soft_codes": sorted({w.code for w in validation.soft_warnings}),
                "status": validation.validation_status.value,
            },
            "contradictions": len(contradictions),
            "severity": label,
            "traffic_delta": round(traffic_delta(features), 4),
            "dq_label": int(any(r.quality_hints.injection_mode for r in reports)),
        })
        return AnomalyOutput(data_quality_anomaly=False, data_quality_score=0.0,
                             situational_anomaly=False, reasons=[])


def generate() -> list[dict]:
    rows: list[dict] = []
    for session_seed, scenario_seed in SESSIONS:
        sim = SimulationState(SeedConfig(session_seed, scenario_seed))
        sim.start(session_seed, scenario_seed)
        engine = JevCityEngine(sim, severity=_StubSeverity(), traffic=_StubTraffic(),
                               anomaly=_ProbeAnomaly(rows))
        plan: list[tuple] = []
        for i, hint in enumerate(HINTS):
            for j, itype in enumerate(TYPES):
                zone = ZONES[(i + j + session_seed) % len(ZONES)]
                plan.append((itype, zone, hint, (i + j) % 3 == 0, None))
        for mode in BAD_MODES:
            plan.append((None, None, None, False, mode))
        for itype, zone, hint, multi, mode in plan:
            if mode is not None:
                sim.inject_bad_data(mode)
            else:
                sim.inject_incident(itype, zone, hint, multi_report=multi)
        engine.process_pending()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO_ROOT / "datasets/jevcity/ml/dataset.jsonl"))
    args = ap.parse_args()
    rows = generate()
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload)
    print(f"{len(rows)} rows -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
