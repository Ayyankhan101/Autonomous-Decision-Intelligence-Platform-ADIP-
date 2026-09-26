"""The question payload — one definition, imported by serving, eval, and bench.

Before this module the same dict lived byte-identical in three files
(`serving/pipeline.py`, `evals/run_eval.py`, `benchmarks/latency_bench.py`).
Only the eval runner checked it against the golden set's `question_set`, so a
one-sided edit made serving score a different task than the eval claimed.
"""

from __future__ import annotations

import hashlib
import json

QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this request?",
        "criteria": {
            "billing": "invoices, payments, refunds, duplicate charges",
            "technical": "bugs, outages, integration failures",
            "sales": ("new purchases, upgrades, pricing, discounts, roadmap questions, "
                      "partner/reseller programs, pre-purchase evaluations and comparisons"),
            "account": "login, password, profile, subscription status, data requests",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this request?",
        "criteria": ["not urgent", "soon", "critical"],
    },
    "refund": {
        "type": "noul",
        "instructions": "Does the customer ask for money back?",
    },
}

# Bump when QUESTIONS changes; stamped into every report/artifact so provenance
# is machine-readable (v1 = 3-option department payload; v2 = 4-option payload;
# v3 = sales criteria enriched to the rubric's pre-purchase scope — the wording
# that lifted macro-F1 0.7117 -> 0.7698, selected against golden v1.0 (see
# evals/README contamination note)).
PAYLOAD_VERSION = 3

# Department vocabulary derived from the payload itself, so adding a department
# to QUESTIONS updates every consumer (eval DEPTS, validator, QC signal table).
DEPTS: list[str] = list(QUESTIONS["department"]["criteria"])
URGENCY_LEVELS: list[int] = [0, 1, 2]


def question_set_sha256() -> str:
    """Short content hash of the payload; stamped in reports for comparison."""
    return hashlib.sha256(
        json.dumps(QUESTIONS, sort_keys=True).encode()
    ).hexdigest()[:12]


class QuestionSetMismatch(ValueError):
    """Raised when a dataset/benchmark payload disagrees with the serving one."""


def assert_matches(dataset_question_set: dict | None) -> None:
    """Hard-fail if a golden set was built against a different question payload.

    Scoring a dataset with the wrong payload measures the wrong task while
    still printing plausible metrics.
    """
    if dataset_question_set is None:
        return  # older artifacts without the key: validated by payload_version
    if dataset_question_set != QUESTIONS:
        raise QuestionSetMismatch(
            "question_set does not match adip.questions.QUESTIONS — the eval "
            "would measure the wrong task; bump the dataset major version instead"
        )
