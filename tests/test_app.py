"""HTTP contract of the FastAPI wrapper (model faked, audit DB in tmp)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch, fake_agent):
    from serving import app as appmod
    from serving.pipeline import DecisionService

    db = tmp_path / "audit.db"
    monkeypatch.setattr(appmod, "svc", DecisionService(audit_path=db))
    monkeypatch.setattr(appmod, "AUDIT_DB", db)
    return TestClient(appmod.app)


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_decide_exposes_privacy_and_latency(client):
    resp = client.post("/decide", json={"text": "refund my duplicate charge"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"decision_id", "route", "decision", "explanation",
                         "privacy", "latency_ms", "vision"}
    assert isinstance(body["privacy"]["redactions"], list)
    assert body["privacy"]["method"].startswith("regex-")


def test_decide_rejects_missing_text(client):
    resp = client.post("/decide", json={"text": ""})
    assert resp.status_code == 422  # pydantic min_length


def test_replay_route_roundtrip(client):
    text = "my card 4111 1111 1111 1111 was charged twice"
    decision_id = client.post("/decide", json={"text": text}).json()["decision_id"]
    ok = client.get(f"/audit/{decision_id}/replay")
    assert ok.status_code == 200
    assert ok.json()["replay_verified"] is True
    assert "[CARD]" not in ok.json()["decision"]["department"]


def test_replay_unknown_id_404(client):
    resp = client.get("/audit/does-not-exist/replay")
    assert resp.status_code == 404


def test_auth_enforced_when_token_set(client, monkeypatch):
    monkeypatch.setenv("ADIP_API_TOKEN", "s3cret")
    assert client.get("/healthz").status_code == 200        # probes stay open
    assert client.post("/decide", json={"text": "hello there"}).status_code == 401
    bad = client.post("/decide", json={"text": "hello there"},
                      headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
    assert bad.headers.get("www-authenticate") == "Bearer"
    ok = client.post("/decide", json={"text": "hello there"},
                     headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_auth_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv("ADIP_API_TOKEN", raising=False)
    assert client.post("/decide", json={"text": "hello there"}).status_code == 200


def test_failed_decide_is_500_and_still_audited(client, monkeypatch):
    from serving import app as appmod

    def boom(text, vision_facts=None):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(appmod.svc, "decide", boom)
    resp = client.post("/decide", json={"text": "hello there"})
    assert resp.status_code == 500
    assert "decision failed: RuntimeError" in resp.json()["detail"]

    import json
    import sqlite3
    conn = sqlite3.connect(appmod.AUDIT_DB)
    decision_id, route, payload = conn.execute(
        "SELECT decision_id, route, decision_json FROM decisions "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert route == "ERROR"
    assert json.loads(payload)["error"] == "RuntimeError"

    # a failed row is replayable as a failure: 409, never a false MISMATCH
    assert client.get(f"/audit/{decision_id}/replay").status_code == 409
    assert "adip_errors_total" in client.get("/metrics").text


def test_metrics_render_counters_and_histograms(client):
    client.post("/decide", json={"text": "hello there"})
    body = client.get("/metrics").text
    assert "adip_decisions_total{" in body
    assert "adip_pipeline_ms_bucket" in body
    assert "adip_stage_ms" in body
