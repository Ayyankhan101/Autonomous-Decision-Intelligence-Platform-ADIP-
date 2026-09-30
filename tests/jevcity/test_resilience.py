"""LIVE resilience: retry policy (C3) + circuit breaker (C4) — model-free via monkeypatch."""
from __future__ import annotations

from datetime import UTC, datetime

from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
from jevcity.schemas import IncidentType, LayaMode, LayaState, LayaStatus, Zone

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _state() -> LayaState:
    return LayaState(
        incident_id="inc-r",
        incident_type=IncidentType.ACCIDENT,
        zone=Zone.NORTH,
        simulated_time=NOW,
        weather="clear",
        traffic_level="low",
        vehicles_involved=1,
        injuries_reported=0,
        lanes_blocked=1,
        severity_prediction="MEDIUM",
        severity_confidence=0.6,
        traffic_congestion_delta=0.1,
        traffic_confidence=0.5,
        data_quality_score=0.0,
        data_quality_reasons=[],
        available_ambulances=3,
        active_competing_incidents=0,
    )


def test_timeout_retried_once_then_timeout(monkeypatch):
    calls: list[int] = []

    def _always_timeout(self, state):
        calls.append(1)
        raise TimeoutError("overrun")

    monkeypatch.setattr(LayaAdapter, "_live_call", _always_timeout)
    response = LayaAdapter(mode=LayaMode.LIVE).ask(_state())
    assert response.status == LayaStatus.TIMEOUT
    assert len(calls) == 2
    assert response.error_code == "live_timeout"


def test_non_timeout_error_fails_fast(monkeypatch):
    calls: list[int] = []

    def _boom(self, state):
        calls.append(1)
        raise RuntimeError("down")

    monkeypatch.setattr(LayaAdapter, "_live_call", _boom)
    response = LayaAdapter(mode=LayaMode.LIVE).ask(_state())
    assert response.status == LayaStatus.UNAVAILABLE
    assert len(calls) == 1
    assert response.error_code == "live_error:RuntimeError"


def test_timeout_then_success_recovers(monkeypatch):
    from tests.jevcity.test_laya_adapter import _FakeLiveAgent

    fake = _FakeLiveAgent()
    attempts = {"n": 0}

    def _flaky(self, state):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TimeoutError("overrun")
        return fake.predict(None, None), 42.0

    monkeypatch.setattr(LayaAdapter, "_live_call", _flaky)
    response = LayaAdapter(mode=LayaMode.LIVE).ask(_state())
    assert response.status == LayaStatus.OK
    assert attempts["n"] == 2
    assert response.latency_ms == 42.0
