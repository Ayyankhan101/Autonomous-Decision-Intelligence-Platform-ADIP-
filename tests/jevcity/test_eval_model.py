"""Real-checkpoint fixture eval (needs laya-mlx checkpoint — model tier only)."""
from __future__ import annotations

import json

import pytest

from tests.test_gates import run

pytestmark = pytest.mark.model


def test_jevcity_eval_exit_mirrors_gates():
    p = run("evals/run_jevcity_eval.py", "--file",
            "fixtures/jevcity_decisions.jsonl", "--strict", "--repeats", "2")
    assert p.returncode in (0, 1), p.stdout + p.stderr
    report_path = next(
        line.split("report: ", 1)[1]
        for line in p.stdout.splitlines()
        if line.startswith("report: ")
    )
    report = json.loads(open(report_path).read())
    assert (p.returncode == 1) == (not report["gates_passed"]), (
        "exit code and gates_passed disagree"
    )
    assert report["gates"] == {"accuracy": 0.70, "ece": 0.15}
    assert report["n"] >= 50
    assert report["accuracy"] == report["accuracy"]
