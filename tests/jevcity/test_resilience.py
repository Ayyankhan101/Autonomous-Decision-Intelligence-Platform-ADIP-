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


def test_breaker_opens_after_three_consecutive_failures(monkeypatch):
    calls: list[int] = []

    def _boom(self, state):
        calls.append(1)
        raise RuntimeError("down")

    monkeypatch.setattr(LayaAdapter, "_live_call", _boom)
    adapter = LayaAdapter(mode=LayaMode.LIVE)
    for _ in range(3):
        response = adapter.ask(_state())
        assert response.status == LayaStatus.UNAVAILABLE
        assert response.error_code == "live_error:RuntimeError"
    assert len(calls) == 3
    assert adapter.health()["breaker_open"] is True
    blocked = adapter.ask(_state())
    assert blocked.status == LayaStatus.UNAVAILABLE
    assert blocked.error_code == "circuit_open"
    assert len(calls) == 3


def test_breaker_half_open_probe_closes_on_success(monkeypatch):
    from tests.jevcity.test_laya_adapter import _FakeLiveAgent

    fake = _FakeLiveAgent()
    state = {"n": 0}

    def _seq(self, s):
        state["n"] += 1
        if state["n"] <= 3:
            raise RuntimeError("down")
        return fake.predict(None, None), 25.0

    monkeypatch.setattr(LayaAdapter, "_live_call", _seq)
    adapter = LayaAdapter(mode=LayaMode.LIVE)
    for _ in range(3):
        adapter.ask(_state())
    assert adapter.health()["breaker_open"] is True
    for _ in range(4):
        blocked = adapter.ask(_state())
        assert blocked.error_code == "circuit_open"
    probe = adapter.ask(_state())
    assert probe.status == LayaStatus.OK
    assert probe.latency_ms == 25.0
    assert adapter.health()["breaker_open"] is False
    followup = adapter.ask(_state())
    assert followup.status == LayaStatus.OK
    assert state["n"] == 5


def test_breaker_probe_failure_keeps_open(monkeypatch):
    calls: list[int] = []

    def _boom(self, state):
        calls.append(1)
        raise RuntimeError("down")

    monkeypatch.setattr(LayaAdapter, "_live_call", _boom)
    adapter = LayaAdapter(mode=LayaMode.LIVE)
    for _ in range(9):
        adapter.ask(_state())
    assert len(calls) == 4
    for _ in range(3):
        blocked = adapter.ask(_state())
        assert blocked.error_code == "circuit_open"
        assert len(calls) == 4
    probe = adapter.ask(_state())
    assert probe.error_code == "live_error:RuntimeError"
    assert len(calls) == 5
    assert adapter.health()["breaker_open"] is True
