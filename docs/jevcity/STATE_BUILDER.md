# Laya State Builder

Plan Phase 0 item 16 (contract approved), §5.4. Source of truth:
`jevcity/decision_engine/laya_adapter/state_builder.py`; narrative also in
`ARCHITECTURE.md` §State builder. Tests: `test_laya_adapter.py`
(`test_notes_never_reach_state_or_render`, `test_adversarial_free_text_is_cleaned_and_bounded`,
`test_build_state_fills_versions`, `test_state_hash_changes_with_state`).

## Principles

- **Compact**: only decision-relevant fields (the English checkpoint has a limited
  context budget — plan §state object guidance).
- **Bounded free text**: `MAX_FREE_TEXT = 64` printable chars; control characters
  stripped. Notes/reports are *cleaned copies*, never raw (Invariant 16).
- **No wall clock**: `simulated_time` comes from the event, never host time.
- **Model outputs enter as contract values**: prediction + confidence + model_version
  (plan item 7), not raw tensors.

## Fields

| Group | Fields |
|---|---|
| Identity | `incident_id`, `incident_type`, `zone`, `simulated_time` |
| Cleaned text | `weather`, `traffic_level` (bounded copies of features) |
| Reported | `vehicles_involved`, `injuries_reported`, `lanes_blocked` |
| Severity model | `severity_prediction`, `severity_confidence`, `severity_model_version` |
| Traffic model | `traffic_congestion_delta` (None unless status ok), `traffic_confidence`, `traffic_model_version` |
| Data quality | `data_quality_score`, `data_quality_reasons` |
| Situation | `available_ambulances`, `active_competing_incidents` |

## Hashing

- `hash_state(state)` — canonical JSON (`sort_keys`, compact separators) →
  `sha256:…`. Used as the adapter cache key component and recorded on decisions
  (`laya.state_hash`) and audit entries (`laya_state_hash`).
- `hash_resources(resources)` — same scheme for the resource snapshot.
- Any state change (model output, availability, clock) changes the hash → cache
  miss → fresh advisory.

## What never enters

Free-text notes, report bodies, adversarial strings (Inv 16), host wall clock,
raw model internals. Adversarial content is handled by the anomaly model and
policy reasons instead (`test_adversarial_notes_flagged_not_followed`).
