"""Guard limits: 413 declared-body cap, 429 per-client rate limit, disable switch.

Guards run in order on /api/*: body cap → rate limit → bearer auth. Both
limits are env-driven read at create_app time; tests pin the limiter off via
the autouse _rate_limit_off fixture."""
from __future__ import annotations

from fastapi.testclient import TestClient

from jevcity.api.app import create_app


def test_body_cap_413(monkeypatch):
    monkeypatch.setenv("JEVCITY_MAX_BODY_BYTES", "16")
    app = create_app()
    with TestClient(app) as c:
        resp = c.post("/api/simulation/pause", json={"note": "x" * 64})
    assert resp.status_code == 413
    assert resp.json()["detail"] == "request body too large"


def test_body_cap_passes_small_body(monkeypatch):
    monkeypatch.setenv("JEVCITY_MAX_BODY_BYTES", "16")
    app = create_app()
    with TestClient(app) as c:
        resp = c.post("/api/simulation/pause")
    assert resp.status_code in (200, 409)  # route ran; cap did not trigger


def test_rate_limit_429_with_retry_after(monkeypatch):
    monkeypatch.setenv("JEVCITY_RATE_LIMIT", "2")
    app = create_app()
    with TestClient(app) as c:
        assert c.get("/api/state").status_code == 200
        assert c.get("/api/state").status_code == 200
        third = c.get("/api/state")
    assert third.status_code == 429
    assert third.json()["detail"] == "rate limit exceeded"
    assert third.headers.get("retry-after") == "30"  # 1 token / (2 per min) = 30s


def test_rate_limit_zero_disables(monkeypatch):
    monkeypatch.setenv("JEVCITY_RATE_LIMIT", "0")
    app = create_app()
    with TestClient(app) as c:
        for _ in range(8):
            assert c.get("/api/state").status_code == 200


def test_static_paths_skip_rate_limit(monkeypatch):
    monkeypatch.setenv("JEVCITY_RATE_LIMIT", "2")
    app = create_app()
    with TestClient(app) as c:
        docs = [c.get("/docs")] + [c.get("/docs") for _ in range(4)]
    assert all(r.status_code == 200 for r in docs)  # threshold untouched by /docs