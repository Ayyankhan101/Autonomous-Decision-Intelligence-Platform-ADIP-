"""The harness gates themselves: each CLI exits non-zero when it must.

These are the regressions this repo shipped with — a failing gate used to
print `gates_passed: false` and still exit 0.
"""

from __future__ import annotations

import json
import subprocess
import sys

from adip.config import REPO_ROOT


def run(*args: str, cwd=REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True,
                          text=True, timeout=300)


def test_selftests_pass():
    for script, flag in [
        ("evals/run_eval.py", "--selftest"),
        ("evals/calibrate.py", "--selftest"),
        ("evals/calibrate_dept.py", "--selftest"),
        ("benchmarks/latency_bench.py", "--selftest"),
    ]:
        p = run(script, flag)
        assert p.returncode == 0, f"{script} {flag}: {p.stdout}{p.stderr}"
        assert "selftest OK" in p.stdout


def test_golden_set_strict_gate_passes():
    p = run("datasets/golden-set/validate.py", "--file",
            "datasets/golden-set/golden-v2.0.json", "--strict", "--expect", "50")
    assert p.returncode == 0, p.stdout + p.stderr


def test_missing_records_key_is_fatal():
    p = run("datasets/golden-set/validate.py", "--file", "pyproject.toml",
            "--strict")
    assert p.returncode == 1
    assert "SystemExit" in p.stderr or "records" in p.stderr


def test_expect_enforced_without_strict():
    p = run("datasets/golden-set/validate.py", "--file",
            "datasets/golden-set/golden-v2.0.json", "--expect", "51")
    assert p.returncode == 1, p.stdout


def test_batch_size_must_be_positive():
    p = run("benchmarks/latency_bench.py", "--batch-size", "0")
    assert p.returncode == 2
    assert "must be >= 1" in p.stderr


def test_calibration_artifact_parses():
    from adip.config import CALIBRATION_ARTIFACT, DEPT_CALIBRATION_ARTIFACT
    art = json.loads((REPO_ROOT / CALIBRATION_ARTIFACT).read_text())
    assert art["schema"] == "adip.calibration.v1"
    assert 0 < art["T_global_fit"] < 5
    dept = json.loads((REPO_ROOT / DEPT_CALIBRATION_ARTIFACT).read_text())
    assert dept["schema"] == "adip.calibration_dept.v1"
    assert 0 < dept["T_global_fit"] < 5
    # strict gate passes both in-sample and out-of-fold (the honest estimate)
    assert dept["gate"]["strict_pass_insample"] is True
    assert dept["gate"]["strict_pass_oof"] is True


def test_qc_sweep_exits_zero_on_frozen_dataset():
    p = run("datasets/golden-set/qc_sweep.py")
    assert p.returncode == 0, p.stdout + p.stderr
