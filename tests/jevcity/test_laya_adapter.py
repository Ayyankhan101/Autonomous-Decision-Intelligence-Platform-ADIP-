from __future__ import annotations

from datetime import UTC, datetime

from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
from jevcity.decision_engine.laya_adapter.normalize import normalize
from jevcity.decision_engine.laya_adapter.questions import QUESTIONS
from jevcity.decision_engine.laya_adapter.state_builder import hash_state
from jevcity.schemas import (
    IncidentType,
    LayaMode,
    LayaRequest,
    LayaState,
    LayaStatus,
    Zone,
)
from jevcity.schemas.laya import ChoiceAnswer

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _state(**overrides) -> LayaState:
    base = dict(
        incident_id="inc-1",
        incident_type=IncidentType.ACCIDENT,
        zone=Zone.NORTH,
        simulated_time=NOW,
        weather="rain",
        traffic_level="high",
        vehicles_involved=3,
        injuries_reported=2,
        lanes_blocked=2,
        severity_prediction="HIGH",
        severity_confidence=0.71,
        traffic_congestion_delta=0.42,
        traffic_confidence=0.58,
        data_quality_score=0.91,
        data_quality_reasons=["contradictory_reports"],
        available_ambulances=0,
        active_competing_incidents=1,
    )
    base.update(overrides)
    return LayaState(**base)


def test_mock_mode_deterministic():
    a = LayaAdapter(mode=LayaMode.MOCK).ask(_state())
    b = LayaAdapter(mode=LayaMode.MOCK).ask(_state())
    assert a.model_dump(mode="json") == b.model_dump(mode="json")
    assert a.state_hash == b.state_hash == hash_state(_state())
    assert a.status == LayaStatus.OK


def test_state_hash_changes_with_state():
    a = LayaAdapter(mode=LayaMode.MOCK).ask(_state())
    b = LayaAdapter(mode=LayaMode.MOCK).ask(_state(data_quality_score=0.1))
    assert a.state_hash != b.state_hash


def test_cache_mode_caches_by_key():
    adapter = LayaAdapter(mode=LayaMode.CACHE)
    first = adapter.ask(_state())
    assert first.status == LayaStatus.OK
    assert len(adapter.cache) == 1
    second = adapter.ask(_state())
    assert second.state_hash == first.state_hash
    # different state → different key → second cache entry
    adapter.ask(_state(available_ambulances=5))
    assert len(adapter.cache) == 2


def test_live_mode_fails_closed_unavailable():
    adapter = LayaAdapter(mode=LayaMode.LIVE)
    response = adapter.ask(_state())
    assert response.status == LayaStatus.UNAVAILABLE
    assert response.error_code == "live_integration_phase3"
    assert response.answers == {}


def test_forced_timeout_status():
    adapter = LayaAdapter(mode=LayaMode.MOCK, force_status=LayaStatus.TIMEOUT)
    response = adapter.ask(_state())
    assert response.status == LayaStatus.TIMEOUT
    assert response.error_code == "forced_timeout"


def test_normalize_rejects_invalid_priority_choice():
    request = LayaRequest(state=_state(), questions=QUESTIONS)
    raw = {
        "priority": {"choice": "APOCALYPSE", "confidence": 0.9,
                     "distribution": {"APOCALYPSE": 0.9}},
        "needs_human_review": {"noul": 0.1},
        "recommended_resource_type": {"choice": "ambulance", "confidence": 0.9},
    }
    response = normalize(
        request, raw, state_hash="sha256:x", questions_hash="sha256:y", latency_ms=1
    )
    assert response.status == LayaStatus.INVALID_RESPONSE  # fail closed, no guessing


def test_normalize_derives_answer_confidence():
    request = LayaRequest(state=_state(), questions=QUESTIONS)
    raw = {
        "priority": {"choice": "HIGH", "confidence": 0.58,
                     "distribution": {"LOW": 0.03, "MEDIUM": 0.18,
                                      "HIGH": 0.58, "CRITICAL": 0.21}},
        "needs_human_review": {"noul": 0.73},
        "recommended_resource_type": {"choice": "ambulance", "confidence": 0.69,
                                      "distribution": {"ambulance": 0.62,
                                                       "police_unit": 0.38}},
    }
    response = normalize(
        request, raw, state_hash="sha256:x", questions_hash="sha256:y", latency_ms=38
    )
    assert response.status == LayaStatus.OK
    answer = response.answers["priority"]
    assert isinstance(answer, ChoiceAnswer)
    # derived from distribution top when upstream field absent (ERRATA C2)
    assert answer.answer_confidence == 0.58


def test_questions_schema_frozen():
    assert set(QUESTIONS) == {"priority", "needs_human_review",
                              "recommended_resource_type"}
    assert QUESTIONS["priority"].type == "choice"
    assert len(QUESTIONS["priority"].criteria) == 4  # option budget (Invariant 13)
    assert len(QUESTIONS["recommended_resource_type"].criteria) == 5
    assert QUESTIONS["needs_human_review"].type == "noul"


def test_state_carries_model_versions():
    from jevcity.decision_engine.laya_adapter.state_text import render_state

    st = _state()
    st2 = st.model_copy(update={"severity_model_version": "sev-gb-1.0.0",
                                "traffic_model_version": "traffic-gbr-1.0.0"})
    text_a = render_state(st2)
    text_b = render_state(st2)
    assert text_a == text_b
    assert "severity_model_version" in text_a
    assert "sev-gb-1.0.0" in text_a
    assert text_a.endswith("\n") is False
    assert len(text_a) < 4096
    assert render_state(st) != text_a


def _primary_event():
    from jevcity.schemas import EventEnvelope, Location, ReportedAttributes

    return EventEnvelope(
        event_id="evt-1", incident_id="inc-1", source_id="s",
        event_type="incident_report", incident_type=IncidentType.ACCIDENT,
        simulated_time=datetime(2026, 9, 27, 10, 0, 1, tzinfo=UTC),
        ingest_time=datetime(2026, 9, 27, 10, 0, 1, tzinfo=UTC),
        location=Location(zone=Zone.NORTH, lat=51.5, lon=-0.14, road_segment_id="rs-1"),
        reported_attributes=ReportedAttributes(),
    )


def test_build_state_fills_versions():
    from jevcity.decision_engine.laya_adapter.state_builder import build_state
    from jevcity.models.severity import SeverityModel
    from jevcity.models.traffic import TrafficModel
    from jevcity.schemas import AnomalyOutput

    st = build_state(
        incident_id="inc-1",
        primary=_primary_event(),
        features={},
        severity=SeverityModel().predict({}),
        traffic=TrafficModel().predict({}),
        anomaly=AnomalyOutput(data_quality_anomaly=False, data_quality_score=0.0,
                              situational_anomaly=False),
        available_ambulances=3,
        active_competing_incidents=0,
    )
    assert st.severity_model_version == "sev-gb-1.0.0"
    assert st.traffic_model_version == "traffic-gbr-1.0.0"


def test_health_probe_reports_runtime_readiness():
    from jevcity.decision_engine.laya_adapter.adapter import DTYPE, LayaAdapter
    from jevcity.schemas import LayaMode

    h = LayaAdapter(mode=LayaMode.MOCK).health()
    assert h == {
        "mode": "mock",
        "runtime": "laya-mlx",
        "checkpoint": "aac6fef/laya-typed-decisions-mlx",
        "router_model": "typed-decisions",
        "device": "mps",
        "dtype": DTYPE,
    }
