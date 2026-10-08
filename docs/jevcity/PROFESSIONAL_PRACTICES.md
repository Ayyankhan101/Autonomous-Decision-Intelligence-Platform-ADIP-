# Professional Practices — fairness, accountability, oversight, privacy, limitations

Plan Phase 6: write-up "tied directly to implemented controls". Every claim below
names the control and its test. JevCity is a **simulated** command center (plan §1) —
scope limits are stated honestly instead of papered over.

## Fairness

- **No protected attributes exist in the pipeline.** Features are incident type,
  zone (geographic), severity hints, model outputs, and resource counts
  (`features/engineer.py`); `LayaState` carries no demographic fields
  (`STATE_BUILDER.md`). Fairness metrics across demographic groups are therefore
  **not computable and not claimed** — what would be needed: incident reports
  containing person-level attributes, a fairness evaluation slice definition, and
  thresholds agreed with stakeholders (post-MVP, plan §10 territory).
- **Zone-level fairness proxy:** allocation prefers same-zone resources
  (`allocate_for_incident`), and contention escalates rather than silently starving a
  zone (`test_contention_escalation_state_not_false_success`). No measured
  cross-zone disparity report exists yet — listed under limitations.
- Synthetic incidents only (seeded simulator); no real-city population to be
  biased against or in favor of.

## Accountability

- **Every automated decision is attributable**: `policy_version`, model versions
  (`sev-gb-1.0.0`, `traffic-gbr-1.0.0`, `anom-ml-1.0.0`,
  `aac6fef/laya-typed-decisions-mlx`), Laya metadata, matched rules, and reasons are
  recorded per decision and per audit entry (Phase 4 contract,
  `test_audit_phase4.py`).
- **Human actions are attributable**: overrides require non-empty `operator_id` and
  `reason` (Invariant 7, API 422, `test_override_entry_records_actor_and_reason`).
- **The record cannot be rewritten**: append-only SQLite triggers (Invariant 8:
  update/delete → ABORT), hash-linked chain with tamper detection
  (`test_update_blocked_by_trigger`, `test_delete_blocked_by_trigger`,
  `test_chain_detects_payload_tamper`), exportable via `python -m jevcity.audit.export`.
- **Routes are frozen**: exactly 16 API endpoints, enforced in CI
  (`test_frozen_routes_preserved_with_dashboard`).
- **Failures are recorded, not hidden**: model errors/timestamps/statuses land in
  the same audit trail (`test_audit_phase4.py`); C4 evaluation gate failure is
  reported as a warning in CI, never suppressed (green-wash policy).

## Human oversight

- **Automation stops where confidence does**: `HOLD_FOR_HUMAN` for low overall
  confidence, low Laya answer confidence, DQ anomalies, model failures, and Laya's
  own review suggestion (`GUARDRAIL.md` rules; `test_guardrail_invariants.py`).
- **Humans outrank the model**: `OVERRIDE_ACTIVE` via `POST /api/overrides`;
  dashboard override modal records actor + reason; Laya suggestions are displayed
  separately from the finalized priority (divergence indicator) — the operator sees
  *proposal vs decision*, never only the model output (`ARCHITECTURE.md` §Decision
  authority, inspector test `test_dashboard_phase5.py`).
- **Uncertainty escalates instead of acting**: `CONTENTION_ESCALATION` when
  resources are short, `MODEL_DEGRADED` on upstream failure (Inv 4), CRITICAL
  blocked without two independent signals (Inv 5) — all human-routing states.
- **What-If stays sandboxed**: isolated Laya cache namespace, no live audit writes,
  `dry_run=true` marked (`test_whatif.py`, Inv 6/15) — operators can rehearse
  without contaminating the record.

## Privacy

- **No personal data in scope**: incidents are synthetic (types, zones, counts);
  no names, IDs, contact details, or location traces of persons exist in the schema
  — nothing to redact (honest scope statement, not a claim of anonymization).
- **Untrusted text never reaches the model raw**: incident notes are stripped of
  control characters and bounded to 64 printable chars before entering any model
  state (Invariant 16, `test_adversarial_free_text_is_cleaned_and_bounded`,
  `test_notes_never_reach_state_or_render`); adversarial instructions in notes are
  treated as data by anomaly/policy (`test_adversarial_notes_flagged_not_followed`).
- **Audit reasons contain machine-generated strings** (rule IDs, model outputs,
  template text) — not raw free-text reports.
- **Model inputs are minimized**: compact `LayaState` only (state-builder fields),
  hashed for integrity; no report bodies, no history dumps.

## Limitations (carried, never green-washed)

1. Laya accuracy/ECE **fail the frozen gates** (0.5675 / 0.3528 vs 0.70 / 0.15,
   n = 84) — advisory trust bounded by guardrail design
   (`LAYA_MODEL_CARD.md`, `CONFIDENCE_CALIBRATION.md`).
2. Confidence uncalibrated (ERRATA C3); dual gates are interim mitigation.
3. Single pinned checkpoint, English-only, float16; `laya-serve` sidecar claims
   unverified (ERRATA C1).
4. Synthetic-only incidents and labels from a baseline-proposer rubric — no
   real-city validation, no fairness measurement.
5. No production auth/scaling/deployment (plan §1 explicitly out of scope).
6. Cross-zone resource-arrival parity unmeasured (see fairness note).
