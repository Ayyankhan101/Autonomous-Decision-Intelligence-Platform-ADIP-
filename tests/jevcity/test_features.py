from __future__ import annotations

from jevcity.features.engineer import history_features
from jevcity.models.encode import columns, dq_vector, encode, explain

FEATURES = {
    "incident_type": "accident", "zone": "north", "hour": 8,
    "time_of_day_bucket": "morning_peak", "weather": "rain",
    "traffic_level": "high", "severity_hint": "severe",
    "vehicles_involved": 4, "injuries_reported": 3, "lanes_blocked": 2,
    "report_count": 1, "zone_share": 0.0, "type_share": 0.0,
}


def test_encode_length_and_determinism():
    vec = encode(FEATURES)
    assert len(vec) == len(columns())
    assert vec == encode(FEATURES)


def test_encode_one_hot_and_defaults():
    vec = encode(FEATURES)
    names = columns()
    assert vec[names.index("incident_type=accident")] == 1.0
    assert vec[names.index("zone=south")] == 0.0
    assert vec[names.index("weather=rain")] == 1.0
    assert vec[names.index("severity_hint=<none>")] == 0.0
    empty = encode({})
    assert len(empty) == len(names)
    assert sum(empty) == 1.0
    assert empty[names.index("severity_hint=<none>")] == 1.0


def test_encode_hint_none_bucket():
    names = columns()
    vec = encode({"severity_hint": None})
    assert vec[names.index("severity_hint=<none>")] == 1.0


def test_explain_lists_nonzero_fields():
    factors = explain(FEATURES, k=4)
    assert 1 <= len(factors) <= 4
    assert any("zone" in f or "weather" in f or "severity" in f for f in factors)


def test_dq_vector_shape_and_flags():
    vec = dq_vector(
        FEATURES, contradiction_count=2, hard_error_count=0,
        soft_codes=["injected_data"], status="accepted",
    )
    assert len(vec) == len(columns()) + 6
    assert vec[-1] == 1.0
    assert vec[-3] == 0.0
    hard = dq_vector(FEATURES, contradiction_count=0, hard_error_count=1,
                     soft_codes=[], status="hard_rejected")
    assert hard[-3] == 1.0


def test_history_features_share():
    from jevcity.simulation.seeds import SeedConfig
    from jevcity.simulation.state import SimulationState

    sim = SimulationState(SeedConfig(42, 7))
    sim.start(42, 7)
    inc = sim.inject_incident("accident", "north", "severe")
    hist = history_features(sim.incidents, "north", "accident", exclude_id=inc)
    assert hist["zone_share"] == 0.0
    hist2 = history_features(sim.incidents, "south", "fire")
    assert hist2["zone_share"] == 0.0 and hist2["type_share"] == 0.0
    hist3 = history_features(sim.incidents, "north", "accident", exclude_id="nope")
    assert hist3["zone_share"] == 1.0 and hist3["type_share"] == 1.0
    assert inc
