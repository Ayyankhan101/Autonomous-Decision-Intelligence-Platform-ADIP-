"""Phase 5 Command Center Dashboard integration and contract tests.

Verifies:
- CORS middleware is active and permits cross-origin dashboard requests.
- Static file serving serves the built dashboard without colliding with /api routes.
- Frozen 16 API endpoints remain exact and intact.
- Human override, What-If sandbox, and fault injection flows work seamlessly.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app
from jevcity.schemas import (
    IncidentType,
    InjectionMode,
    OverrideType,
    Priority,
    WhatIfScenario,
    Zone,
)
from tests.jevcity.test_audit_phase4 import FROZEN_ROUTES

_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
_SKIP_NO_DIST = pytest.mark.skipif(
    not _DIST.exists(),
    reason="dashboard/dist absent — run: cd dashboard && pnpm build (CI builds before pytest)",
)


def test_cors_headers_present():
    app = create_app(build_engine())
    client = TestClient(app)
    res = client.get("/api/state", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


def test_frozen_routes_preserved_with_dashboard():
    app = create_app(build_engine())
    api_routes = {
        (sorted(r.methods - {"HEAD", "OPTIONS"})[0], r.path)
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/")
    }
    assert api_routes == FROZEN_ROUTES


@_SKIP_NO_DIST
def test_dashboard_static_assets_served():
    app = create_app(build_engine())
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "JevCity" in res.text or "html" in res.text


def test_dashboard_simulation_controls_flow():
    app = create_app(build_engine())
    client = TestClient(app)

    # Start simulation
    r_start = client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    assert r_start.status_code == 200

    # Inject incident
    r_inc = client.post(
        "/api/simulation/incident",
        json={
            "incident_type": IncidentType.ACCIDENT.value,
            "zone": Zone.EAST.value,
            "severity": "moderate",
            "source_id": "dashboard-sensor-01",
            "notes": "two-vehicle collision blocking lane",
        },
    )
    assert r_inc.status_code == 200
    inc_data = r_inc.json()
    assert inc_data["ok"] is True
    incident_id = inc_data["incident_id"]
    assert incident_id is not None
    assert len(inc_data["decision_ids"]) == 1
    decision_id = inc_data["decision_ids"][0]

    # Verify decision is accessible
    r_dec = client.get(f"/api/decisions/{decision_id}")
    assert r_dec.status_code == 200
    dec_record = r_dec.json()
    assert dec_record["decision_id"] == decision_id
    assert dec_record["priority"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    # Apply human override
    r_ovr = client.post(
        "/api/overrides",
        json={
            "operator_id": "op-commander-09",
            "decision_id": decision_id,
            "override_type": OverrideType.CHANGE_PRIORITY.value,
            "reason": "field observer confirms toxic plume hazard",
            "new_priority": Priority.CRITICAL.value,
        },
    )
    assert r_ovr.status_code == 200
    ovr_record = r_ovr.json()
    assert ovr_record["operator_id"] == "op-commander-09"
    assert ovr_record["previous_priority"] == dec_record["priority"]

    # Verify audit log recorded override
    r_audit = client.get("/api/audit")
    assert r_audit.status_code == 200
    entries = r_audit.json()["entries"]
    override_entries = [e for e in entries if e["action"] == "OVERRIDE_APPLIED"]
    assert len(override_entries) >= 1
    assert override_entries[0]["actor"] == "op-commander-09"

    # Test What-If counterfactual execution
    r_wf = client.post(
        "/api/what-if/run",
        json={"scenario": WhatIfScenario.REMOVE_ONE_AMBULANCE.value},
    )
    assert r_wf.status_code == 200
    wf_data = r_wf.json()
    assert wf_data["dry_run"] is True
    assert wf_data["audit_written"] is False
    assert wf_data["live_state_mutated"] is False
    sandbox_id = wf_data["sandbox_id"]

    # Retrieve stored What-If result
    r_wf_res = client.get(f"/api/what-if/{sandbox_id}/result")
    assert r_wf_res.status_code == 200
    assert r_wf_res.json()["sandbox_id"] == sandbox_id

    # Test bad-data injection
    r_bad = client.post(
        "/api/simulation/bad-data",
        json={"mode": InjectionMode.ADVERSARIAL_NOTES.value},
    )
    assert r_bad.status_code == 200
    assert r_bad.json()["ok"] is True

    # Test second emergency injection
    r_sec = client.post(
        "/api/simulation/second-emergency",
        json={"incident_type": IncidentType.FIRE.value, "zone": Zone.NORTH.value},
    )
    assert r_sec.status_code == 200
    assert r_sec.json()["ok"] is True
