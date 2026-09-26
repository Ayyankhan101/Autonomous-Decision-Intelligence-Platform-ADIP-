"""Honesty contract: the strict exit code must mirror `gates_passed`.

Needs the laya-mlx checkpoint, so it runs in the model tier only
(`pytest -m model`), not on every PR.
"""

from __future__ import annotations

import json

import pytest

from tests.test_gates import run

pytestmark = pytest.mark.model


def test_strict_exit_code_mirrors_gate_state():
    p = run("evals/run_eval.py", "--file",
            "datasets/golden-set/golden-v2.0.json", "--strict",
            "--repeats", "2")
    assert p.returncode in (0, 1), p.stdout + p.stderr
    report_path = next(line.split("report: ", 1)[1]
                       for line in p.stdout.splitlines()
                       if line.startswith("report: "))
    report = json.loads(open(report_path).read())
    assert (p.returncode == 1) == (not report["gates_passed"]), (
        "exit code and gates_passed disagree — the bug this repo shipped with"
    )
    assert report["refund"]["temperature_applied"] == 0.45
    assert report["refund"]["ece"] < report["refund"]["ece_raw"]  # temp helps
    assert report["department"]["temperature_applied"] == 0.6
    assert report["department"]["ece"] < report["department"]["ece_raw"]
