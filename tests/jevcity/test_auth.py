"""Auth middleware: ADIP_API_TOKEN guards /api/*, unset = open dev mode.

Mirrors tests/test_app.py auth tests for the serving app — same env var,
same 401 contract, one secret for both ADIP surfaces."""
from __future__ import annotations


def test_auth_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv("ADIP_API_TOKEN", raising=False)
    assert client.get("/api/state").status_code == 200


def test_auth_enforced_when_token_set(client, monkeypatch):
    monkeypatch.setenv("ADIP_API_TOKEN", "s3cret")
    denied = client.get("/api/state")
    assert denied.status_code == 401
    assert denied.headers.get("www-authenticate") == "Bearer"
    bad = client.get("/api/state", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
    scheme = client.get("/api/state", headers={"Authorization": "Token s3cret"})
    assert scheme.status_code == 401  # non-bearer scheme rejected
    ok = client.get("/api/state", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_write_route_guarded_too(client, monkeypatch):
    monkeypatch.setenv("ADIP_API_TOKEN", "s3cret")
    assert client.post("/api/simulation/pause").status_code == 401


def test_docs_stay_open_when_token_set(client, monkeypatch):
    monkeypatch.setenv("ADIP_API_TOKEN", "s3cret")
    # browser navigation cannot send a bearer header; non-/api paths exempt
    assert client.get("/docs").status_code == 200
