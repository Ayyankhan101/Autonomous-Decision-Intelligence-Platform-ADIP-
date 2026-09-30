from __future__ import annotations

import json
from pathlib import Path

from jevcity.schemas import LayaState, Priority, ResourceType

FIXTURES = Path("fixtures/jevcity_decisions.jsonl")


def _rows():
    return [json.loads(line) for line in FIXTURES.read_text().splitlines() if line.strip()]


def test_fixture_count_and_schema():
    rows = _rows()
    assert len(rows) >= 50
    for row in rows:
        assert set(row) == {"state", "expected"}
        state = LayaState.model_validate(row["state"])
        assert state.incident_id
        expected = row["expected"]
        assert set(expected) == {"priority", "needs_human_review",
                                 "recommended_resource_type"}
        assert expected["priority"] in {p.value for p in Priority}
        assert isinstance(expected["needs_human_review"], bool)
        assert expected["recommended_resource_type"] in {r.value for r in ResourceType}


def test_fixture_states_carry_model_versions():
    rows = _rows()
    versioned = [r for r in rows if r["state"].get("severity_model_version")]
    assert len(versioned) == len(rows)


def test_fixture_labels_cover_all_priorities():
    rows = _rows()
    priorities = {r["expected"]["priority"] for r in rows}
    assert priorities == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    reviews = {r["expected"]["needs_human_review"] for r in rows}
    assert reviews == {True, False}
