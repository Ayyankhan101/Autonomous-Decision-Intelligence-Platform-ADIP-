"""Laya state builder (plan §5.4, Phase 0 item 16): compact, decision-relevant fields only;
bounded free text never enters state raw (Invariant 16 — notes handled by anomaly/policy)."""
from __future__ import annotations

import hashlib
import json

from jevcity.schemas import AnomalyOutput, EventEnvelope, LayaState, ModelOutput, Resource

MAX_FREE_TEXT = 64


def _clean_free_text(value: str | None) -> str | None:
    """Bounded, control-char-free copy of free text (Invariant 16)."""
    if value is None:
        return None
    printable = "".join(ch for ch in value if ch.isprintable())
    return printable[:MAX_FREE_TEXT]


def build_state(
    *,
    incident_id: str,
    primary: EventEnvelope,
    features: dict,
    severity: ModelOutput,
    traffic: ModelOutput,
    anomaly: AnomalyOutput,
    available_ambulances: int,
    active_competing_incidents: int,
) -> LayaState:
    return LayaState(
        incident_id=incident_id,
        incident_type=primary.incident_type,
        zone=primary.location.zone,
        simulated_time=primary.simulated_time,
        weather=_clean_free_text(features.get("weather")),
        traffic_level=_clean_free_text(features.get("traffic_level")),
        vehicles_involved=features.get("vehicles_involved"),
        injuries_reported=features.get("injuries_reported"),
        lanes_blocked=features.get("lanes_blocked"),
        severity_prediction=severity.prediction,
        severity_confidence=severity.confidence,
        traffic_congestion_delta=(
            float(traffic.prediction) if traffic.status.value == "ok" else None
        ),
        traffic_confidence=traffic.confidence,
        severity_model_version=severity.model_version,
        traffic_model_version=traffic.model_version,
        data_quality_score=anomaly.data_quality_score,
        data_quality_reasons=anomaly.reasons,
        available_ambulances=available_ambulances,
        active_competing_incidents=active_competing_incidents,
    )


def hash_state(state: LayaState) -> str:
    payload = json.dumps(state.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def hash_resources(resources: list[Resource]) -> str:
    payload = json.dumps(
        [r.model_dump(mode="json") for r in resources], sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
