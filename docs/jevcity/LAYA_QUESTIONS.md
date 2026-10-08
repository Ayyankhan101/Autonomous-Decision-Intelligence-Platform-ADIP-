# Laya Question Templates — `q-0.1.0`

Plan §3.1.1 / Phase 0 item 17 (approved, validated live Phase 3 C6). Source of truth:
`jevcity/decision_engine/laya_adapter/questions.py` — this doc mirrors it;
`tests/jevcity/test_laya_adapter.py::test_questions_schema_frozen` fails on any change.

**Version:** `QUESTIONS_VERSION = "q-0.1.0"` — recorded on every audit entry as
`laya_questions_version` and hashed into the adapter cache key (`hash_questions`).

## Questions (3, no score questions — Invariant 14)

### `priority` — type `choice` (4 options = option budget, Invariant 13)

Instructions: *"What operational priority should this incident receive?"*

| Option | Criteria |
|---|---|
| LOW | routine |
| MEDIUM | needs attention |
| HIGH | significant risk |
| CRITICAL | immediate life-safety or major city impact |

### `needs_human_review` — type `noul` (2 labels)

Instructions: *"Should this incident be held for human review before automation acts?"*

| Label | Criteria |
|---|---|
| A (`true`) | yes, a human operator must review |
| B (`false`) | no, automated handling ok |

### `recommended_resource_type` — type `choice` (5 options = option budget)

Instructions: *"What primary resource type is most appropriate?"*

| Option | Criteria |
|---|---|
| ambulance | medical response required |
| fire_truck | fire or rescue required |
| police_unit | traffic control or security required |
| flood_response_unit | flooding response required |
| traffic_management_unit | congestion management required |

## Budgets and validation

- Priority = 4 options, resource = 5 options — both within the plan's safe MVP budget
  (plan §risk 13: no high-cardinality choice questions without shortlisting).
- The normalizer rejects distributions containing options outside these sets
  (`_validate_distribution`, tested in `tests/jevcity/test_laya_schema_battery.py`).
- Adding options later requires: a new `QUESTIONS_VERSION`, schema export
  (`uv run python -m jevcity.schemas.export`), and frozen-question test updates.
