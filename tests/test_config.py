"""The regression gate for every constant in adip.config.

The shipped calibration temperature must equal the fit recorded in the
committed artifact; otherwise serving applies a temperature nobody fit.
"""

from __future__ import annotations

import json

import pytest

from adip import config
from adip.questions import DEPTS


def test_serving_temperature_matches_committed_artifact():
    artifact = json.loads((config.REPO_ROOT / config.CALIBRATION_ARTIFACT).read_text())
    assert artifact["T_global_fit"] == config.REFUND_TEMPERATURE, (
        "adip.config.REFUND_TEMPERATURE drifted from the fit in "
        f"{config.CALIBRATION_ARTIFACT}; update config or refit deliberately"
    )
    assert artifact["gate_pass_after_calibration"] is True
    assert artifact["ece_calibrated_oof"] < config.GATE_ECE_REFUND
    assert artifact["ece_raw_oof"] >= config.GATE_ECE_REFUND  # calibration earns the gate


def test_dept_temperature_matches_committed_artifact():
    artifact = json.loads((config.REPO_ROOT / config.DEPT_CALIBRATION_ARTIFACT).read_text())
    assert artifact["T_global_fit"] == config.DEPT_TEMPERATURE, (
        "adip.config.DEPT_TEMPERATURE drifted from the fit in "
        f"{config.DEPT_CALIBRATION_ARTIFACT}; update config or refit deliberately"
    )
    assert artifact["gate"]["strict_pass_insample"] is True
    assert artifact["gate"]["strict_pass_oof"] is True
    # calibration earns the gate: raw head could never clear 0.15
    assert artifact["ece_raw"] >= config.GATE_ECE_DEPT
    assert artifact["ece_calibrated"] < config.GATE_ECE_DEPT


def test_router_thresholds_are_ordered():
    assert config.CONF_REVIEW < config.CONF_AUTO <= 1.0
    assert 0.0 <= config.REFUND_THRESHOLD < config.REFUND_REVIEW_HI <= 1.0


def test_gate_and_kpi_limits_are_ordered():
    # strict bar sits below the aspirational target it replaced (D6)
    assert 0 < config.GATE_MACRO_F1 < config.GATE_MACRO_F1_TARGET <= 1.0
    assert 0 < config.GATE_URGENCY_ACCURACY < config.GATE_URGENCY_ACCURACY_TARGET <= 1.0
    # interim calibration bars sit LOOSER (higher) than the aspirational target
    assert config.GATE_ECE_TARGET < config.GATE_ECE_DEPT_TARGET < config.GATE_ECE_DEPT
    assert config.GATE_ECE_DEPT < config.GATE_ECE_TARGET * 10
    assert config.GATE_ECE_TARGET < config.GATE_ECE_URGENCY < config.GATE_ECE_TARGET * 10
    assert config.GATE_ECE_REFUND == config.GATE_ECE_TARGET == 0.05  # refund kept strict
    assert config.GATE_DECISION_P50_MS < config.KPI_P50_MS < config.KPI_P95_MS
    assert config.GATE_LATENCY_P95_TARGET_MS < config.KPI_P50_MS


def test_dataset_and_artifact_paths_resolve():
    golden = json.loads((config.REPO_ROOT / config.GOLDEN_SET_DEFAULT).read_text())
    assert len(golden["records"]) == 50
    assert golden["version"] == "v2.0"
    assert (config.REPO_ROOT / config.CALIBRATION_ARTIFACT).is_file()
    assert (config.REPO_ROOT / config.DEPT_CALIBRATION_ARTIFACT).is_file()


def test_department_vocabulary_matches_dataset_labels(golden):
    used = {r["labels"]["department"] for r in golden["records"]}
    assert used <= set(DEPTS)
    assert used == set(DEPTS), "every department must appear in the golden set"


def test_payload_version_is_integer():
    from adip.questions import PAYLOAD_VERSION
    assert isinstance(PAYLOAD_VERSION, int) and PAYLOAD_VERSION >= 2


@pytest.mark.parametrize("name", ["CHECKPOINT", "DTYPE", "BATCH_SIZE"])
def test_model_settings_present(name):
    assert getattr(config, name) is not None
