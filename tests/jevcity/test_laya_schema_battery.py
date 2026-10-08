"""Phase 6 (F2): Laya response-schema / failure battery (plan §6 "Laya schema tests",
option budget Invariant 13, probability validation).

Sidecar-only failure modes (malformed JSON, checkpoint download failure, out of memory,
invalid device) do not apply to the in-process laya-mlx runtime (ERRATA C1) and are
documented in docs/jevcity/LAYA_FAILURE_MODES.md instead of being faked here.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jevcity.decision_engine.laya_adapter.normalize import normalize, to_raw
from jevcity.decision_engine.laya_adapter.questions import QUESTIONS
from jevcity.schemas import (
    IncidentType,
    LayaRequest,
    LayaState,
    LayaStatus,
    Zone,
)

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _request() -> LayaRequest:
    state = LayaState(
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
    return LayaRequest(state=state, questions=QUESTIONS)


def _ok_raw() -> dict:
    return {
        "priority": {
            "choice": "HIGH",
            "confidence": 0.58,
            "answer_confidence": 0.58,
            "distribution": {"LOW": 0.03, "MEDIUM": 0.18, "HIGH": 0.58, "CRITICAL": 0.21},
        },
        "needs_human_review": {"noul": 0.4, "answer_confidence": 0.6},
        "recommended_resource_type": {
            "choice": "ambulance",
            "confidence": 0.69,
            "answer_confidence": 0.69,
            "distribution": {"ambulance": 0.62, "police_unit": 0.38},
        },
    }


def _run(raw: dict):
    return normalize(
        _request(), raw, state_hash="sha256:x", questions_hash="sha256:y", latency_ms=1
    )


# --- to_raw: upstream shape extraction fails closed -------------------------------


def test_to_raw_empty_result_returns_none():
    assert to_raw({}) is None
    assert to_raw({"answers": {}}) is None


def test_to_raw_missing_resource_answer_returns_none():
    raw = {"answers": {"priority": {"probabilities": {"HIGH": 0.9}},
                       "needs_human_review": {"noul": 0.2}}}
    assert to_raw(raw) is None


def test_to_raw_missing_noul_answer_returns_none():
    raw = {"answers": {"priority": {"probabilities": {"HIGH": 0.9}},
                       "recommended_resource_type": {"probabilities": {"ambulance": 1.0}}}}
    assert to_raw(raw) is None


def test_to_raw_noul_out_of_range_returns_none():
    raw = {"answers": {"priority": {"probabilities": {"HIGH": 0.9}},
                       "needs_human_review": {"noul": 1.5},
                       "recommended_resource_type": {"probabilities": {"ambulance": 1.0}}}}
    assert to_raw(raw) is None


def test_to_raw_non_numeric_probabilities_returns_none():
    raw = {"answers": {"priority": {"probabilities": {"HIGH": "a lot"}},
                       "needs_human_review": {"noul": 0.2},
                       "recommended_resource_type": {"probabilities": {"ambulance": 1.0}}}}
    assert to_raw(raw) is None


def test_to_raw_derives_choice_from_distribution_when_absent():
    raw = {"answers": {"priority": {"probabilities": {"LOW": 0.1, "CRITICAL": 0.9}},
                       "needs_human_review": {"noul": 0.2},
                       "recommended_resource_type": {"probabilities": {"ambulance": 1.0}}}}
    out = to_raw(raw)
    assert out is not None
    assert out["priority"]["choice"] == "CRITICAL"
    assert out["priority"]["answer_confidence"] == 0.9


# --- normalize: validation failures are INVALID_RESPONSE (Invariant 12) -----------


def test_missing_priority_answer_fails():
    raw = _ok_raw()
    del raw["priority"]
    response = _run(raw)
    assert response.status == LayaStatus.INVALID_RESPONSE
    assert response.error_code and response.error_code.startswith("invalid_output:")


def test_invalid_priority_choice_fails():
    raw = _ok_raw()
    raw["priority"]["choice"] = "URGENT"
    assert _run(raw).status == LayaStatus.INVALID_RESPONSE


def test_invalid_resource_choice_fails():
    raw = _ok_raw()
    raw["recommended_resource_type"]["choice"] = "spaceship"
    assert _run(raw).status == LayaStatus.INVALID_RESPONSE


def test_noul_out_of_range_fails():
    raw = _ok_raw()
    raw["needs_human_review"]["noul"] = -0.2
    assert _run(raw).status == LayaStatus.INVALID_RESPONSE


def test_negative_probability_fails():
    raw = _ok_raw()
    raw["priority"]["distribution"]["HIGH"] = -0.5
    response = _run(raw)
    assert response.status == LayaStatus.INVALID_RESPONSE
    assert "out of range" in (response.error_code or "")


def test_probability_sum_error_fails():
    raw = _ok_raw()
    raw["priority"]["distribution"] = {"LOW": 0.4, "MEDIUM": 0.4, "HIGH": 0.4}
    response = _run(raw)
    assert response.status == LayaStatus.INVALID_RESPONSE
    assert "sum out of range" in (response.error_code or "")


def test_unknown_priority_option_fails_option_budget():
    raw = _ok_raw()
    raw["priority"]["distribution"]["APOCALYPSE"] = 0.5
    response = _run(raw)
    assert response.status == LayaStatus.INVALID_RESPONSE
    assert "unknown options" in (response.error_code or "")


def test_extra_fields_are_ignored():
    raw = _ok_raw()
    raw["bonus_field"] = {"unexpected": True}
    raw["priority"]["bonus_key"] = "ignored"
    response = _run(raw)
    assert response.status == LayaStatus.OK


@pytest.mark.parametrize("noul", [0.0, 1.0])
def test_noul_bounds_accepted(noul):
    raw = _ok_raw()
    raw["needs_human_review"]["noul"] = noul
    assert _run(raw).status == LayaStatus.OK


def test_happy_path_answers_complete():
    response = _run(_ok_raw())
    assert response.status == LayaStatus.OK
    assert set(response.answers) == {
        "priority", "needs_human_review", "recommended_resource_type"
    }
    priority = response.answers["priority"]
    assert priority.choice == "HIGH"
    assert abs(sum(priority.distribution.values()) - 1.0) < 1e-9
