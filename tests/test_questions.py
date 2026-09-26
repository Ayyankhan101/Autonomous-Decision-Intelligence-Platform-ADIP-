"""One payload, imported everywhere — verified against the golden set."""

from __future__ import annotations

import pytest

from adip.questions import (DEPTS, PAYLOAD_VERSION, QUESTIONS, URGENCY_LEVELS,
                            QuestionSetMismatch, assert_matches,
                            question_set_sha256)


def test_payload_shape():
    assert set(QUESTIONS) == {"department", "urgency", "refund"}
    assert QUESTIONS["department"]["type"] == "choice"
    assert QUESTIONS["urgency"]["type"] == "score"
    assert QUESTIONS["refund"]["type"] == "noul"
    assert set(QUESTIONS["department"]["criteria"]) == set(DEPTS)


def test_vocabulary_derived_not_duplicated():
    assert URGENCY_LEVELS == list(range(len(QUESTIONS["urgency"]["criteria"])))
    assert DEPTS == list(QUESTIONS["department"]["criteria"])


def test_matches_golden_question_set(golden):
    assert_matches(golden["question_set"])  # raises QuestionSetMismatch on drift


def test_mismatch_is_loud():
    broken = {"department": dict(QUESTIONS["department"]),
              "urgency": dict(QUESTIONS["urgency"]),
              "refund": dict(QUESTIONS["refund"])}
    broken["department"] = dict(QUESTIONS["department"], criteria={"only": "one"})
    with pytest.raises(QuestionSetMismatch):
        assert_matches(broken)


def test_sha256_is_stable_and_payload_versioned():
    a = question_set_sha256()
    b = question_set_sha256()
    assert a == b and len(a) == 12
    assert PAYLOAD_VERSION == 3
    # payload v3 = sales criteria enriched to the rubric's pre-purchase scope;
    # pin the hash so a silent question edit fails here, not in the eval report
    assert a == "13393cd59b87"
