"""ADIP vision evidence: POST /images + /decide image_ids (model faked, audit in tmp)."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

PNG_B64 = base64.b64encode(Path("fixtures/vision/scene.png").read_bytes()).decode()


@pytest.fixture
def audit_db(tmp_path):
    return tmp_path / "audit.db"


@pytest.fixture
def client(tmp_path, monkeypatch, fake_agent, audit_db):
    from serving import app as appmod
    from serving.pipeline import DecisionService
    from vision.store import ImageStore

    monkeypatch.setattr(appmod, "svc", DecisionService(audit_path=audit_db))
    monkeypatch.setattr(appmod, "AUDIT_DB", audit_db)
    store = ImageStore(tmp_path / "images")
    monkeypatch.setattr(appmod, "_STORE", store)
    return TestClient(appmod.app)


def test_upload_and_decide_with_evidence(client):
    up = client.post("/images", json={"image_b64": PNG_B64})
    assert up.status_code == 200
    body = up.json()
    assert len(body["image_id"]) == 64
    assert body["mime"] == "image/png"
    assert body["facts"]["status"] == "ok"
    image_id = body["image_id"]

    r = client.post("/decide", json={
        "text": "customer cannot log in after password reset",
        "image_ids": [image_id],
    })
    assert r.status_code == 200
    out = r.json()
    assert out["vision"]  # evidence echoed
    assert "[vision:" in out["explanation"]  # rides in the explanation
    # routing gates untouched: same decision without evidence
    plain = client.post("/decide", json={"text": "customer cannot log in after password reset"})
    assert plain.json()["decision"] == out["decision"]


def test_decide_unknown_image_id_is_422(client):
    r = client.post("/decide", json={"text": "some ticket text here",
                                     "image_ids": ["0" * 64]})
    assert r.status_code == 422


def test_decide_without_image_ids_contract_unchanged(client):
    r = client.post("/decide", json={"text": "refund request for order 123"})
    assert r.status_code == 200
    assert r.json()["vision"] == []


def test_upload_bad_image_422(client):
    assert client.post("/images", json={"image_b64": ""}).status_code == 422
    assert client.post("/images",
                       json={"image_b64": base64.b64encode(b"nope").decode()}
                       ).status_code == 422


def test_replay_still_matches_with_vision_evidence(client, audit_db):
    up = client.post("/images", json={"image_b64": PNG_B64}).json()
    r = client.post("/decide", json={
        "text": "customer cannot log in after password reset",
        "image_ids": [up["image_id"]],
    })
    assert r.status_code == 200

    from serving.pipeline import replay
    result = replay(r.json()["decision_id"], audit_path=audit_db)
    assert result["matches"] is True
