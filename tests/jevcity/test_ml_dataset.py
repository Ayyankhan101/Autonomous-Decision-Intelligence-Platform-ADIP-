from __future__ import annotations

import json
from pathlib import Path

from jevcity.models.traffic import TrafficModel, traffic_delta

DATASET = Path("datasets/jevcity/ml/dataset.jsonl")


def test_traffic_delta_matches_model_heuristic():
    features = {"lanes_blocked": 2, "traffic_level": "high", "vehicles_involved": 4}
    out = TrafficModel().predict(features)
    assert out.prediction == f"{traffic_delta(features):.2f}"


def test_dataset_rows_complete_and_split_covering():
    rows = [json.loads(line) for line in DATASET.read_text().splitlines()]
    assert len(rows) >= 250
    train = [r for i, r in enumerate(rows) if i % 5 != 0]
    held = [r for i, r in enumerate(rows) if i % 5 == 0]
    assert len(held) >= 40 and train
    labels = {r["severity"] for r in rows}
    assert labels == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert {r["dq_label"] for r in rows} == {0, 1}
    for row in rows:
        assert set(row) == {"features", "validation", "contradictions",
                            "severity", "traffic_delta", "dq_label"}
        assert row["features"]["severity_hint"] in ("minor", "moderate", "severe")
        assert 0.0 <= row["traffic_delta"] <= 1.0


def test_dataset_regeneration_is_deterministic(tmp_path, monkeypatch):
    import subprocess
    import sys

    before = DATASET.read_bytes()
    subprocess.run(
        [sys.executable, "tools/gen_ml_dataset.py", "--out", str(tmp_path / "d.jsonl")],
        check=True, capture_output=True,
    )
    assert (tmp_path / "d.jsonl").read_bytes() == before
