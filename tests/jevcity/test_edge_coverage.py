"""Coverage-driven edge pack: error paths, guard branches, and rarely-taken
edges that the feature-oriented suites never hit (raises jevcity coverage
from 96% toward the hard-to-reach branches)."""
from __future__ import annotations

import json
import random
import sqlite3
import time
from datetime import UTC, datetime, timedelta

import pytest

from jevcity.audit.export import AuditExportError, export_entries
from jevcity.audit.log import AuditLog
from jevcity.decision_engine.guardrail.policy import _priority_or_low
from jevcity.decision_engine.lineage import build_lineage, pick_clause
from jevcity.ingestion.correlate import correlate
from jevcity.ingestion.trust import TrustRegistry
from jevcity.ingestion.validate import validate_raw
from jevcity.models.ml_data import load_dataset
from jevcity.simulation import bad_data as bad_data_mod
from jevcity.simulation.bad_data import InjectionMode, apply_bad_data, pick_mode
from jevcity.simulation.clock import EPOCH, SimClock
from jevcity.simulation.event_gen import EventGenerator
from jevcity.simulation.replay import load_recording, stream
from jevcity.simulation.resource_pool import ResourcePool
from jevcity.schemas import (
    ChoiceAnswer,
    DataQualitySignal,
    IncidentType,
    LayaMode,
    LayaState,
    LayaStatus,
    ModelOutput,
    ModelStatus,
    NormalizedLayaResponse,
    NoulAnswer,
    OverrideType,
    PolicyPosition,
    Priority,
    SeverityHint,
    SeveritySignal,
    Signals,
    TrafficSignal,
    ValidationStatus,
    WhatIfRequest,
    WhatIfScenario,
    Zone,
)

from jevcity.decision_engine.laya_adapter import adapter as adapter_mod
from jevcity.decision_engine.laya_adapter.adapter import (
    answer_confidence_priority,
    recommended_resource_type,
    suggested_needs_human_review,
    suggested_priority,
)
from jevcity.decision_engine.laya_adapter.state_builder import hash_resources

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _event_dict(
    *,
    event_id: str,
    source_id: str = "sensor-a",
    severity: str = "severe",
    zone: str = "east",
    road: str = "rs-01",
    injuries: int | None = 1,
    incident_id: str = "inc-00001",
    when: datetime = NOW,
) -> dict:
    return {
        "event_id": event_id,
        "incident_id": incident_id,
        "source_id": source_id,
        "event_type": "incident_report",
        "incident_type": "accident",
        "simulated_time": when.isoformat(),
        "ingest_time": when.isoformat(),
        "location": {"zone": zone, "lat": 51.5, "lon": -0.14, "road_segment_id": road},
        "reported_attributes": {
            "severity": severity,
            "vehicles_involved": 2,
            "injuries_reported": injuries,
            "lanes_blocked": 1,
            "notes": None,
        },
        "context": {
            "weather": "clear",
            "traffic_level": "moderate",
            "time_of_day_bucket": None,
        },
        "quality_hints": {"is_synthetic": False, "injection_mode": None},
    }


def _event(**kw):
    from jevcity.schemas import EventEnvelope

    return EventEnvelope.model_validate(_event_dict(**kw))


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


# --- simulation clock ----------------------------------------------------


def test_clock_advance_reset_and_all_daypart_buckets():
    clock = SimClock()
    assert clock.now == EPOCH
    clock.advance(5)
    assert clock.now == EPOCH + timedelta(seconds=5)
    clock.reset()
    assert clock.now == EPOCH

    buckets = {
        8: "morning_peak",
        17: "evening_peak",
        12: "day",
        23: "night",
        4: "night",
    }
    for hour, expected in buckets.items():
        when = datetime(2026, 9, 27, hour, 0, tzinfo=UTC)
        assert SimClock.time_of_day_bucket(when) == expected


# --- bad-data injection ---------------------------------------------------


def test_apply_bad_data_covers_every_mode_and_rejects_unknown():
    conflicting = apply_bad_data({}, InjectionMode.CONFLICTING_REPORTS)
    assert conflicting["reported_attributes"]["injuries_reported"] == 17
    assert conflicting["quality_hints"]["injection_mode"] == "conflicting_reports"

    adversarial = apply_bad_data({}, InjectionMode.ADVERSARIAL_NOTES)
    assert adversarial["reported_attributes"]["notes"] == bad_data_mod.ADVERSARIAL_NOTE

    missing = apply_bad_data({}, InjectionMode.MISSING_FIELDS)
    assert missing["quality_hints"]["injection_mode"] == "missing_fields"

    for mode in InjectionMode:
        out = apply_bad_data({}, mode)
        assert out["quality_hints"]["is_synthetic"] is True

    with pytest.raises(ValueError, match="unknown injection mode"):
        apply_bad_data({}, "not-a-mode")

    assert isinstance(pick_mode(random.Random(0)), InjectionMode)


# --- resource pool --------------------------------------------------------


def test_pool_double_assign_busy_and_unknown_id_errors():
    pool = ResourcePool.default()
    rid = pool.all()[0].resource_id
    pool.assign(rid, "inc-00001")
    with pytest.raises(ValueError, match="not available"):
        pool.assign(rid, "inc-00002")

    pool.set_busy(rid)
    assert pool.get(rid).status.value == "busy"

    with pytest.raises(KeyError, match="unknown resource"):
        pool.release("res-nope")
    pool.release(rid)
    assert pool.get(rid).status.value == "available"


# --- ingestion ------------------------------------------------------------


def test_correlate_reports_every_contradiction_kind():
    with pytest.raises(ValueError, match="no reports"):
        correlate([])

    base = dict(event_id="evt-1", source_id="s1")
    severity_clash = correlate(
        [
            _event(**base, severity="severe"),
            _event(event_id="evt-2", source_id="s2", severity="minor"),
        ]
    )
    assert "contradictory_reports" in severity_clash.contradictions

    zone_clash = correlate(
        [_event(**base, zone="east"), _event(event_id="evt-2", source_id="s2", zone="north")]
    )
    assert "conflicting_location" in zone_clash.contradictions

    injury_clash = correlate(
        [_event(**base, injuries=1), _event(event_id="evt-2", source_id="s2", injuries=9)]
    )
    assert "conflicting_injury_count" in injury_clash.contradictions

    road_clash = correlate(
        [_event(**base, road="rs-01"), _event(event_id="evt-2", source_id="s2", road="rs-02")]
    )
    assert "conflicting_road_segment" in road_clash.contradictions
    assert road_clash.has_contradiction is True


def test_trust_empty_observation_and_empty_mean_are_noops():
    registry = TrustRegistry()
    registry.observe([])
    assert registry.mean_veracity([]) == 1.0
    assert registry.flagged() == []


def test_validate_severe_without_injuries_emits_soft_finding():
    result = validate_raw(_event_dict(event_id="evt-1", severity="severe", injuries=0))
    codes = [f.code for f in result.soft_warnings]
    assert "missing_injury_count" in codes
    assert result.validation_status is not ValidationStatus.HARD_REJECTED


# --- guardrail helpers -----------------------------------------------------


def test_priority_or_low_covers_all_three_branches():
    sev = ModelOutput(
        status=ModelStatus.OK,
        model_name="sev-rule",
        model_version="0.1.0",
        prediction="CRITICAL",
        confidence=0.9,
        latency_ms=1.0,
    )
    assert _priority_or_low(sev) is Priority.HIGH

    sev_ok = sev.model_copy(update={"prediction": "MEDIUM"})
    assert _priority_or_low(sev_ok) is Priority.MEDIUM

    failed = sev.model_copy(update={"status": ModelStatus.ERROR, "prediction": None})
    assert _priority_or_low(failed) is Priority.LOW


# --- event generation ------------------------------------------------------


def test_make_incident_requires_simulated_when():
    gen = EventGenerator(random.Random(1), random.Random(2))
    with pytest.raises(ValueError, match="never use wall clock"):
        gen.make_incident(IncidentType.FIRE, Zone.NORTH)


def test_make_incident_without_jitter_is_moderate():
    gen = EventGenerator(random.Random(1), random.Random(2))
    event = gen.make_incident(
        IncidentType.FLOOD,
        Zone.SOUTH,
        when=NOW,
        severity_jitter=False,
    )
    assert event.reported_attributes.severity is SeverityHint.MODERATE


# --- replay ----------------------------------------------------------------


def test_load_recording_missing_file_and_invalid_row(tmp_path):
    with pytest.raises(ValueError, match="must live under"):
        load_recording(tmp_path / "nope.jsonl")
    with pytest.raises(ValueError, match="not readable"):
        load_recording("definitely-missing-recording.jsonl")

    bad = tmp_path / "bad.jsonl"
    bad.write_text("\nnot-json-at-all\n")
    with pytest.raises(ValueError, match="invalid event row"):
        load_recording(bad, base=tmp_path)


def test_stream_rejects_wrong_sim_and_nonpositive_speed(engine):
    with pytest.raises(TypeError, match="SimulationState"):
        stream(object(), [], speed=1.0, sleeper=lambda _s: None)
    with pytest.raises(ValueError, match="speed must be > 0"):
        stream(engine.simulation, [], speed=0, sleeper=lambda _s: None)


# --- lineage ---------------------------------------------------------------


def test_pick_clause_empty_unknown_and_precedence():
    assert pick_clause([]) is None
    assert pick_clause(["R-ZZZ-NOT-A-RULE"]) == "R-ZZZ-NOT-A-RULE"
    assert pick_clause(["R-AUTO-APPROVE-01", "R-INPUT-REJECT-01"]) == "R-INPUT-REJECT-01"


def test_build_lineage_uses_priority_weight_when_confidence_absent():
    signals = Signals(
        severity=SeveritySignal(status=ModelStatus.OK, prediction="HIGH", confidence=None),
        traffic=TrafficSignal(),
        data_quality=DataQualitySignal(data_quality_score=0.9),
    )
    block = build_lineage(signals, ["R-AUTO-APPROVE-01"])
    sev_term = next(t for t in block.terms if t.label == "severity_model")
    assert sev_term.score == pytest.approx(0.75)


# --- ml dataset ------------------------------------------------------------


def test_load_dataset_rejects_empty_and_degenerate_splits(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    with pytest.raises(ValueError, match="empty dataset"):
        load_dataset(empty)

    single = tmp_path / "single.jsonl"
    single.write_text('{"x": 1}\n')
    with pytest.raises(ValueError, match="degenerate split"):
        load_dataset(single)


# --- laya adapter internals -------------------------------------------------


def test_adapter_runtime_label_and_answer_helpers_on_wrong_answer_types():
    adapter = adapter_mod.LayaAdapter(mode=LayaMode.MOCK)
    assert "(mock)" in adapter.runtime

    base = dict(
        status=LayaStatus.OK,
        runtime="rt",
        checkpoint="cp",
        router_model="rm",
        device="cpu",
        state_hash="sha256:h",
        questions_hash="sha256:q",
    )
    noul_priority = NormalizedLayaResponse(
        **base, answers={"priority": NoulAnswer(noul=0.9, answer_confidence=0.4)}
    )
    assert suggested_priority(noul_priority) is None
    assert answer_confidence_priority(noul_priority) is None

    choice = ChoiceAnswer(choice="HIGH", confidence=0.9, answer_confidence=0.7, distribution={})
    wrong_nhr = NormalizedLayaResponse(**base, answers={"needs_human_review": choice})
    assert suggested_needs_human_review(wrong_nhr) is None
    wrong_res = NormalizedLayaResponse(
        **base,
        answers={"recommended_resource_type": NoulAnswer(noul=1.0, answer_confidence=0.5)},
    )
    assert recommended_resource_type(wrong_res) is None


def test_hash_resources_is_order_sensitive_and_deterministic(engine):
    resources = engine.simulation.pool.all()
    first = hash_resources(resources)
    assert first == hash_resources(resources)
    assert first.startswith("sha256:")
    assert hash_resources(list(reversed(resources))) != first


def test_live_thread_path_propagates_agent_error(monkeypatch):
    def _no_agent():
        raise RuntimeError("checkpoint missing")

    monkeypatch.setattr(adapter_mod, "_live_agent", _no_agent)
    response = adapter_mod.LayaAdapter(mode=LayaMode.LIVE).ask(_state())
    assert response.status is LayaStatus.UNAVAILABLE
    assert response.error_code == "live_error:RuntimeError"


def test_live_thread_path_times_out_slow_agent(monkeypatch):
    class _Slow:
        def predict(self, text, questions):
            time.sleep(3)
            return {"answers": {}}

    monkeypatch.setattr(adapter_mod, "_live_agent", lambda: _Slow())
    response = adapter_mod.LayaAdapter(mode=LayaMode.LIVE, live_timeout_s=0.05).ask(_state())
    assert response.status is LayaStatus.TIMEOUT
    assert response.error_code == "live_timeout"


# --- engine guards ----------------------------------------------------------


def test_decide_for_guards_reports_removed_after_processing(engine):
    incident_id = engine.simulation.inject_incident(
        IncidentType.FIRE, Zone.NORTH, multi_report=True
    )
    records = engine.process_pending()
    assert records
    engine.simulation.events = [
        e for e in engine.simulation.events if e.incident_id != incident_id
    ]
    with pytest.raises(KeyError, match="no reports for incident"):
        engine.decide_for(
            incident_id,
            pool=engine.simulation.pool,
            adapter=engine.adapter,
        )


def test_validation_for_without_reports_raises(engine):
    with pytest.raises(ValueError, match="no reports"):
        engine._validation_for("inc-ghost", [])


def test_latest_decision_returns_none_for_unknown_incident(engine):
    assert engine._latest_decision("inc-ghost") is None


def test_assess_override_without_recommended_resources(engine):
    engine.simulation.inject_incident(IncidentType.FLOOD, Zone.SOUTH)
    record = engine.process_pending()[0]
    engine.decisions[record.decision_id] = record.model_copy(
        update={"recommended_resources": []}
    )
    assessment = engine.assess_override(
        record.decision_id, OverrideType.CHANGE_PRIORITY, Priority.MEDIUM
    )
    assert assessment.warning
    assert assessment.tier is not None


def test_policy_switch_skips_incidents_without_decisions(engine):
    engine.simulation.inject_incident(IncidentType.ACCIDENT, Zone.EAST)
    report = engine.switch_policy(PolicyPosition.EQUITY, reoptimise_active=True)
    assert report["position"] is PolicyPosition.EQUITY
    assert report["affected_decisions"] == []
    assert report["reoptimised"] == 0


# --- api guards --------------------------------------------------------------


def test_what_if_run_conflicts_when_no_decidable_incidents(client):
    response = client.post("/api/what-if/run", json={"scenario": "close_road"})
    assert response.status_code == 409
    assert "no decidable incidents" in response.json()["detail"]


def test_audit_entries_filter_by_decision_id(client, engine):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    created = client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north"},
    )
    decision_id = created.json()["decision_ids"][0]
    filtered = engine.audit.entries(decision_id=decision_id)
    assert filtered
    assert all(e.decision_id == decision_id for e in filtered)
    assert engine.audit.entries(decision_id="dec-zzzzzz") == []


def test_audit_verify_survives_non_json_payload(client, engine):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "fire", "zone": "east"},
    )
    engine.audit._conn.execute("DROP TRIGGER audit_no_update")
    engine.audit._conn.execute("UPDATE audit_log SET payload = '{\"broken' WHERE rowid = 1")
    engine.audit._conn.commit()

    out = client.get("/api/audit/verify").json()
    assert out["ok"] is False
    assert out["broken_at"] == 1


def test_validate_chain_catches_missing_linkage(client, engine):
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north"},
    )
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "flood", "zone": "south"},
    )
    assert engine.audit.validate_chain() is True

    engine.audit._conn.execute("DROP TRIGGER audit_no_update")
    engine.audit._conn.execute("DROP TRIGGER audit_no_delete")
    engine.audit._conn.execute("DELETE FROM audit_log WHERE rowid = 1")
    engine.audit._conn.commit()
    assert engine.audit.validate_chain() is False


def test_export_raises_on_previous_hash_mismatch(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    log.append(actor="system", action="DECISION_EMITTED", reason="first")
    log.append(actor="system", action="DECISION_EMITTED", reason="second")
    path = log.path
    log.close()

    conn = sqlite3.connect(path)
    conn.executescript("DROP TRIGGER audit_no_update; DROP TRIGGER audit_no_delete;")
    row = conn.execute(
        "SELECT payload FROM audit_log WHERE entry_id = 'aud-000002'"
    ).fetchone()
    tampered = json.loads(row[0])
    tampered["previous_hash"] = "sha256:0000000000000000"
    conn.execute(
        "UPDATE audit_log SET payload = ? WHERE entry_id = 'aud-000002'",
        (json.dumps(tampered),),
    )
    conn.commit()
    conn.close()

    with pytest.raises(AuditExportError, match="previous_hash mismatch"):
        export_entries(path)


def _seed_decidable(engine) -> None:
    engine.simulation.inject_incident(IncidentType.FIRE, Zone.NORTH)
    engine.process_pending()


def _live_snapshot(engine) -> dict:
    sim = engine.simulation
    return {
        "clock": sim.simulated_time,
        "incidents": set(sim.incidents),
        "raw": len(sim.raw_events),
        "events": len(sim.events),
        "fired": sim.second_emergency_fired,
        "incident_counter": sim.generator._incident_counter,
        "event_counter": sim.generator._event_counter,
        "engine_counter": engine._counter,
        "veracity": dict(engine.trust.veracity),
        "availability": dict(engine.trust.availability),
        "audit": engine.audit.chain_report()["entry_count"],
        "rng_session": sim.session_rng.getstate(),
        "rng_scenario": sim.scenario_rng.getstate(),
        "processed": engine._processed,
        "pool": sorted(
            (r.resource_id, str(r.status), r.assigned_incident_id)
            for r in sim.pool.all()
        ),
        "decisions": len(engine.decisions),
        "history": len(engine.decision_history),
        "validations": len(engine.validation_by_event),
    }


@pytest.mark.parametrize(
    "scenario",
    ["second_emergency", "remove_one_ambulance", "close_road"],
)
def test_what_if_leaves_zero_live_residue(engine, scenario):
    _seed_decidable(engine)
    before = _live_snapshot(engine)
    result = engine.run_what_if(WhatIfRequest(scenario=WhatIfScenario(scenario)))
    assert result.live_state_mutated is False
    assert result.audit_written is False
    after = _live_snapshot(engine)
    assert after == before


def test_what_if_second_emergency_repeat_is_deterministic_and_unique(engine):
    _seed_decidable(engine)
    first = engine.run_what_if(WhatIfRequest(scenario=WhatIfScenario.SECOND_EMERGENCY))
    second = engine.run_what_if(WhatIfRequest(scenario=WhatIfScenario.SECOND_EMERGENCY))
    assert first.sandbox_id != second.sandbox_id
    assert (
        first.decision.priority,
        first.decision.state,
        tuple(first.decision.matched_rules),
    ) == (
        second.decision.priority,
        second.decision.state,
        tuple(second.decision.matched_rules),
    )


def test_next_live_incident_id_after_what_if_has_no_gap(engine):
    _seed_decidable(engine)
    expected_next = engine.simulation.generator._incident_counter + 1
    engine.run_what_if(WhatIfRequest(scenario=WhatIfScenario.SECOND_EMERGENCY))
    injected = engine.simulation.inject_incident(IncidentType.FLOOD, Zone.SOUTH)
    assert injected == f"inc-{expected_next:05d}"
