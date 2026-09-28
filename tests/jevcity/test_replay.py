from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app
from jevcity.simulation.replay import load_recording, stream

RECORDING = Path("datasets/jevcity/sim-session-v1.jsonl")


def test_load_recording_valid():
    events = load_recording(RECORDING)
    assert len(events) >= 8
    assert events == sorted(events, key=lambda e: e.simulated_time)
    assert len({e.event_id for e in events}) == len(events)


def test_load_rejects_path_escape(tmp_path):
    with pytest.raises(ValueError, match="datasets/jevcity"):
        load_recording("../../etc/passwd")


def test_load_rejects_invalid_row(tmp_path):
    bad = tmp_path / "bad.jsonl"
    good = RECORDING.read_text().splitlines()[0]
    bad.write_text(good + "\n" + '{"event_id": "broken"}\n')
    with pytest.raises(ValueError, match=":2:"):
        load_recording(bad, base=tmp_path)


def _replay_decisions(speed: float):
    engine = build_engine()
    engine.simulation.start(42, 7)
    records = load_recording(RECORDING)
    stream(engine.simulation, records, speed=speed, sleeper=lambda _s: None)
    out = engine.process_pending()
    return [(r.incident_id, r.state, r.priority) for r in out]


def test_replay_deterministic_across_speeds():
    assert _replay_decisions(1.0) == _replay_decisions(25.0)
    assert len(_replay_decisions(1.0)) >= 6


def test_replay_pacing_scales_with_speed():
    engine = build_engine()
    engine.simulation.start(42, 7)
    records = load_recording(RECORDING)
    slept: list[float] = []
    stream(engine.simulation, records, speed=2.0, sleeper=slept.append)
    gaps = [
        (b.simulated_time - a.simulated_time).total_seconds()
        for a, b in zip(records, records[1:])
    ]
    assert slept == [g / 2.0 for g in gaps if g > 0]


def test_replay_clock_follows_recording_timeline():
    engine = build_engine()
    engine.simulation.start(42, 7)
    records = load_recording(RECORDING)
    stream(engine.simulation, records, speed=7.5, sleeper=lambda _s: None)
    assert engine.simulation.simulated_time == records[-1].simulated_time


def test_api_start_with_recording():
    client = TestClient(create_app())
    r = client.post(
        "/api/simulation/start",
        json={"session_seed": 42, "scenario_seed": 7,
              "recording": "sim-session-v1.jsonl", "speed": 5.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["decision_ids"]) >= 6
    state = client.get("/api/state").json()
    assert state["incident_count"] >= 6


def test_api_start_bad_recording_422():
    client = TestClient(create_app())
    r = client.post(
        "/api/simulation/start",
        json={"session_seed": 42, "scenario_seed": 7, "recording": "../etc/passwd"},
    )
    assert r.status_code == 422


def test_load_rejects_unsorted(tmp_path):
    rows = RECORDING.read_text().splitlines()
    unsorted_file = tmp_path / "unsorted.jsonl"
    unsorted_file.write_text(rows[1] + "\n" + rows[0] + "\n")
    with pytest.raises(ValueError, match="non-decreasing"):
        load_recording(unsorted_file, base=tmp_path)


def test_load_rejects_fractional_seconds(tmp_path):
    import json

    row = json.loads(RECORDING.read_text().splitlines()[0])
    row["simulated_time"] = "2026-09-27T10:00:01.500Z"
    frac = tmp_path / "frac.jsonl"
    frac.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="whole seconds"):
        load_recording(frac, base=tmp_path)
