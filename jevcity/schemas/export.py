"""Export frozen contracts as JSON Schema for the dashboard/frontend (Phase 0 item 10)."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

MODELS = {
    "event_envelope": "EventEnvelope",
    "model_output": "ModelOutput",
    "anomaly_output": "AnomalyOutput",
    "validation_result": "ValidationResult",
    "resource": "Resource",
    "incident_record": "IncidentRecord",
    "laya_request": "LayaRequest",
    "normalized_laya_response": "NormalizedLayaResponse",
    "decision_record": "DecisionRecord",
    "audit_entry": "AuditEntry",
    "state_payload": "StatePayload",
    "override_request": "OverrideRequest",
    "impact_preview_request": "ImpactPreviewRequest",
    "impact_preview_response": "ImpactPreviewResponse",
    "audit_verify_response": "AuditVerifyResponse",
    "laya_mode_request": "LayaModeRequest",
    "laya_mode_response": "LayaModeResponse",
    "policy_position_request": "PolicyPositionRequest",
    "policy_position_response": "PolicyPositionResponse",
    "what_if_request": "WhatIfRequest",
    "what_if_result": "WhatIfResult",
}


def export(out_dir: str | Path = "schemas") -> list[Path]:
    import jevcity.schemas as s

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for slug, name in MODELS.items():
        model: type[BaseModel] = getattr(s, name)
        path = out / f"{slug}.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for p in export():
        print(p)
