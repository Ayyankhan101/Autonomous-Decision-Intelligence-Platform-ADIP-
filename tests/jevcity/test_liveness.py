"""Demo-liveness pack: live hash-chain verify + runtime Laya mode toggle."""
from __future__ import annotations

import pytest


def test_audit_verify_intact_chain(client, engine):
    _start(client)
    _inject(client)
    r = client.get("/api/audit/verify")
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is True
    assert out["broken_at"] is None
    assert out["entry_count"] >= 1


def test_audit_verify_detects_tamper(client, engine):
    _start(client)
    _inject(client)
    r = client.get("/api/audit/verify")
    assert r.json()["ok"] is True

    # tamper: an attacker who bypasses the append-only SQL trigger (drop it) still
    # gets caught by the hash chain (valid JSON, altered field → hash mismatch)
    engine.audit._conn.execute("DROP TRIGGER audit_no_update")
    engine.audit._conn.execute(
        "UPDATE audit_log SET payload = "
        "replace(payload, '\"actor\":\"system\"', '\"actor\":\"intruder\"') "
        "WHERE rowid = 1"
    )
    engine.audit._conn.commit()

    r = client.get("/api/audit/verify")
    assert r.status_code == 200
    out = r.json()
    assert out["ok"] is False
    assert out["broken_at"] == 1
    assert out["entry_count"] >= 1
    # validate_chain (legacy bool API) stays consistent
    assert engine.audit.validate_chain() is False


def test_laya_mode_toggle_mock_cache(client, engine):
    _start(client)
    r = client.post("/api/simulation/laya-mode", json={"mode": "cache"})
    assert r.status_code == 200
    out = r.json()
    assert out["previous_mode"] == "mock"
    assert out["mode"] == "cache"
    assert engine.adapter.mode.value == "cache"
    state = client.get("/api/state").json()
    assert state["laya_mode"] == "cache"

    # switching back is idempotent-safe
    r = client.post("/api/simulation/laya-mode", json={"mode": "mock"})
    assert r.status_code == 200
    assert r.json() == {"previous_mode": "cache", "mode": "mock"}
    assert client.get("/api/state").json()["laya_mode"] == "mock"


def test_laya_mode_invalid_rejected(client):
    _start(client)
    r = client.post("/api/simulation/laya-mode", json={"mode": "quantum"})
    assert r.status_code == 422
    r = client.post("/api/simulation/laya-mode", json={"mode": "live", "extra": 1})
    assert r.status_code == 422  # extra=forbid


def test_laya_mode_live_constructs(client, engine):
    """Live adapter constructs lazily — no model load at toggle time."""
    _start(client)
    r = client.post("/api/simulation/laya-mode", json={"mode": "live"})
    assert r.status_code == 200
    assert r.json() == {"previous_mode": "mock", "mode": "live"}
    assert engine.adapter.mode.value == "live"
    assert client.get("/api/state").json()["laya_mode"] == "live"


@pytest.mark.laya_live
def test_laya_mode_live_decides(client, engine):
    """After a live switch, injected incidents still route (fail-closed)."""
    _start(client)
    r = client.post("/api/simulation/laya-mode", json={"mode": "live"})
    assert r.status_code == 200

    body = _inject(client)
    assert len(body["decision_ids"]) == 1
    rec = client.get(f"/api/decisions/{body['decision_ids'][0]}").json()
    assert rec["laya"] is not None
    assert rec["laya"]["status"]


def _start(client):
    r = client.post(
        "/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7}
    )
    assert r.status_code == 200


def _inject(client, incident_type="accident", zone="north", severity="severe"):
    r = client.post(
        "/api/simulation/incident",
        json={"incident_type": incident_type, "zone": zone, "severity": severity},
    )
    assert r.status_code == 200
    return r.json()
