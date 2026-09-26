"""Golden-set integrity: the same checks the strict CLI gate runs, in-process."""

from __future__ import annotations

import sys

from adip.config import GOLDEN_SET_DEFAULT, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "datasets/golden-set"))
import validate  # noqa: E402


def test_every_record_passes_strict_validation(golden):
    errors: list[str] = []
    for i, rec in enumerate(golden["records"]):
        validate.check_record(rec, i, errors)
    assert errors == []


def test_composition_matches_expectation(golden):
    errors: list[str] = []
    warnings: list[str] = []
    validate.composition(golden["records"], 50, errors, warnings)
    assert errors == []
    assert len(golden["records"]) == 50


def test_dataset_version_field_present(golden):
    assert golden["version"] == "v2.0"
    assert golden["dataset"] == "ticket-triage"


def test_v2_changed_questions_not_labels(golden):
    """Major bump rule: question-set change = new version, labels untouched."""
    import json
    v1 = json.loads((REPO_ROOT / "datasets/golden-set/golden-v1.0.json").read_text())
    assert golden["records"] == v1["records"]
    assert golden["question_set"] != v1["question_set"]
    assert v1["version"] == "v1.0"


def test_load_records_helper_reads_default_path():
    recs = validate.load_records(REPO_ROOT / GOLDEN_SET_DEFAULT)
    assert len(recs) == 50


def test_ids_unique_and_label_key_shape(golden):
    ids = [r["ticket_id"] for r in golden["records"]]
    assert len(set(ids)) == len(ids)
    for rec in golden["records"]:
        assert set(rec["labels"]) == {"department", "urgency", "refund"}
        assert set(rec) == {"ticket_id", "text", "labels", "language", "source", "meta"}
