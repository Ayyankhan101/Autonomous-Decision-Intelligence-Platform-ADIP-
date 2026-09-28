from __future__ import annotations

from jevcity.ingestion.correlate import correlate
from jevcity.ingestion.validate import validate_raw
from jevcity.schemas import (
    InjectionMode,
    ValidationStatus,
    WhatIfRequest,
    WhatIfScenario,
)
from jevcity.simulation.bad_data import ADVERSARIAL_NOTE, apply_bad_data
from jevcity.simulation.event_gen import EventGenerator
from jevcity.simulation.seeds import SeedConfig, build_rngs
from jevcity.simulation.state import SimulationState
from jevcity.schemas import IncidentType, SeverityHint, Zone


def _gen(seed=42) -> EventGenerator:
    session, scenario = build_rngs(SeedConfig(seed, seed + 1))
    return EventGenerator(session, scenario)


def test_seed_determinism_same_events():
    from datetime import UTC, datetime

    when = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
    a = _gen(42).make_incident(IncidentType.ACCIDENT, Zone.NORTH, when=when)
    b = _gen(42).make_incident(IncidentType.ACCIDENT, Zone.NORTH, when=when)
    assert a.model_dump(mode="json") == b.model_dump(mode="json")


def test_different_seeds_diverge():
    from datetime import UTC, datetime

    when = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
    a = _gen(42).make_incident(IncidentType.ACCIDENT, Zone.NORTH, when=when)
    b = _gen(99).make_incident(IncidentType.ACCIDENT, Zone.NORTH, when=when)
    assert a.location != b.location or a.reported_attributes != b.reported_attributes


def test_simulated_clock_not_wall_clock():
    state = SimulationState(SeedConfig(42, 7))
    first = state.simulated_time
    state.inject_incident(IncidentType.FIRE, Zone.SOUTH, SeverityHint.MINOR)
    assert state.simulated_time > first
    assert state.simulated_time.year == 2026  # simulated epoch, not host now()


def test_multi_report_correlation_and_contradiction(engine):
    incident_id = engine.simulation.inject_incident(
        IncidentType.ACCIDENT, Zone.NORTH, SeverityHint.MODERATE, multi_report=True
    )
    reports = engine.simulation.reports_for(incident_id)
    assert len(reports) == 2
    result = correlate(reports)
    assert result.has_contradiction
    assert "contradictory_reports" in result.contradictions


def test_hard_injection_rejected(engine):
    incident_id = engine.simulation.inject_incident(
        IncidentType.FIRE, Zone.SOUTH, bad_data_mode=InjectionMode.OUT_OF_RANGE
    )
    records = engine.process_pending()
    record = records[-1]
    assert record.incident_id == incident_id
    assert record.state.value == "REJECTED_INPUT"
    assert record.laya is None  # never reached Laya


def test_adversarial_notes_flagged_not_followed(engine):
    incident_id = engine.simulation.inject_incident(
        IncidentType.TRAFFIC_SPIKE,
        Zone.CENTRAL,
        SeverityHint.MINOR,
        notes=ADVERSARIAL_NOTE,
    )
    record = engine.process_pending()[-1]
    # treated as data: soft-flagged, not obeyed as instruction
    assert not (
        record.state.value == "AUTO_APPROVED" and record.priority.value == "CRITICAL"
    )
    validation = next(
        v for v in engine.validation_by_event.values() if v.incident_id == incident_id
    )
    assert any(w.code == "free_text_notes_present" for w in validation.soft_warnings)


def test_validation_paths():
    valid = _valid_event()
    result = validate_raw(valid)
    assert result.validation_status == ValidationStatus.VALID
    assert result.data_quality_score == 0.0

    missing = apply_bad_data(valid, InjectionMode.MISSING_FIELDS)
    hard = validate_raw(missing)
    assert hard.validation_status == ValidationStatus.HARD_REJECTED
    assert hard.data_quality_score == 1.0
    assert hard.hard_errors


def test_second_emergency_rolls_back_after_what_if(engine):
    engine.simulation.inject_incident(IncidentType.ACCIDENT, Zone.NORTH, SeverityHint.SEVERE)
    engine.process_pending()
    before_events = len(engine.simulation.raw_events)
    before_incidents = len(engine.simulation.incidents)
    engine.run_what_if(
        WhatIfRequest(scenario=WhatIfScenario.SECOND_EMERGENCY)
    )
    assert len(engine.simulation.raw_events) == before_events
    assert len(engine.simulation.incidents) == before_incidents


def _valid_event() -> dict:
    return {
        "event_id": "evt-1",
        "incident_id": "inc-1",
        "source_id": "s1",
        "incident_type": "accident",
        "simulated_time": "2026-09-27T10:00:00+00:00",
        "ingest_time": "2026-09-27T10:00:01+00:00",
        "location": {"zone": "north", "lat": 51.5, "lon": -0.1, "road_segment_id": "rs-1"},
        "reported_attributes": {
            "severity": "minor",
            "vehicles_involved": 1,
            "injuries_reported": 0,
            "lanes_blocked": 1,
        },
    }
