from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jevcity.schemas import (
    DecisionRecord,
    EventEnvelope,
    ModelOutput,
    ModelStatus,
    OverrideRequest,
    OverrideType,
    Priority,
    Signals,
)


def _event(**overrides) -> dict:
    base = {
        "event_id": "evt-000001",
        "incident_id": "inc-00001",
        "source_id": "sensor-01",
        "incident_type": "accident",
        "simulated_time": "2026-09-27T10:14:00+00:00",
        "ingest_time": "2026-09-27T10:14:02+00:00",
        "location": {"zone": "north", "lat": 51.5, "lon": -0.14, "road_segment_id": "rs-18"},
        "reported_attributes": {
            "severity": "minor",
            "vehicles_involved": 2,
            "injuries_reported": 0,
            "lanes_blocked": 1,
        },
    }
    base.update(overrides)
    return base


def test_event_envelope_frozen_contract():
    event = EventEnvelope.model_validate(_event())
    assert event.event_type == "incident_report"
    assert event.quality_hints.is_synthetic is True
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_event(extra_field="nope"))


def test_event_rejects_out_of_range():
    raw = _event()
    raw["location"]["lat"] = 999.0
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


def test_notes_bounded():
    raw = _event()
    raw["reported_attributes"]["notes"] = "x" * 501
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(raw)


def test_model_output_contract():
    out = ModelOutput(
        status=ModelStatus.OK,
        model_name="m",
        model_version="v1",
        prediction="HIGH",
        confidence=0.7,
        latency_ms=12,
    )
    assert out.error_code is None
    failed = ModelOutput.failed("m", "v1", ModelStatus.TIMEOUT, error_code="MODEL_FAILURE")
    assert failed.prediction is None and failed.confidence is None


def test_override_requires_actor_and_reason():
    with pytest.raises(ValidationError):
        OverrideRequest(
            operator_id="",
            decision_id="dec-1",
            override_type=OverrideType.CHANGE_PRIORITY,
            reason="x",
        )
    with pytest.raises(ValidationError):
        OverrideRequest(
            operator_id="op",
            decision_id="dec-1",
            override_type=OverrideType.CHANGE_PRIORITY,
            reason="",
        )


def test_decision_record_separates_state_and_priority():
    signals = Signals.model_construct(
        severity=None, traffic=None, data_quality=None
    )
    record = DecisionRecord.model_construct(
        decision_id="dec-1",
        incident_id="inc-1",
        state="HOLD_FOR_HUMAN",
        priority="CRITICAL",
        signals=signals,
        reasons=[],
        matched_rules=[],
        decision_time_simulated=datetime(2026, 9, 27, 10, 0, tzinfo=UTC),
    )
    assert record.state != record.priority
    assert Priority(record.priority) == Priority.CRITICAL
