# Guardrail — deterministic policy authority

Plan §3.3 (Policy Invariants), §5.8, Phase 6 guardrail documentation (signoff item 28).
Source of truth: `jevcity/decision_engine/guardrail/policy.py` + `confidence.py` +
`allocate.py`. **Laya proposes; policy decides** — the guardrail is the safety case,
not the model (`LAYA_MODEL_CARD.md` measured-below-gate).

## Invariants 1–16 (plan §3.3) → evidence

| # | Invariant (short) | Evidence |
|---|---|---|
| 1 | Hard invalid input cannot produce automated priority | `test_inv1_hard_invalid_never_auto_decides` |
| 2 | DQ anomaly cannot produce CRITICAL without human | `test_inv2_dq_anomaly_blocks_critical_auto` |
| 3 | Low confidence cannot auto-decide | `test_inv3_low_confidence_holds` |
| 4 | Model failure cannot auto-decide | `test_inv4_model_failure_degrades` (parametrized), `test_inv4_anomaly_failure_fails_closed` |
| 5 | CRITICAL needs ≥ 2 independent model signals | `test_inv5_single_signal_cannot_critical` / `…_two_signals_allow_critical` |
| 6 | What-If dry-run cannot write live decisions/audit | `test_what_if_never_writes_live_audit`, `test_what_if_never_mutates_live_state`, `test_dry_run_entries_rejected` |
| 7 | Override requires actor and reason | API `OverrideRequest` min_length=1 (422), `test_override_entry_records_actor_and_reason` |
| 8 | Audit entries cannot be updated/deleted via APIs | SQLite ABORT triggers, `test_update_blocked_by_trigger`, `test_delete_blocked_by_trigger` |
| 9 | Laya output cannot bypass deterministic validation | `test_inv9_laya_invalid_fails_closed`, normalize battery (`test_laya_schema_battery.py`) |
| 10 | Laya alone cannot force CRITICAL (structurally ineligible signal) | `test_inv10_laya_alone_cannot_force_critical`, `test_laya_not_counted_as_independent_signal` |
| 11 | Laya confidence thresholds must be recalibrated (not copied) | `CONFIDENCE_CALIBRATION.md`; gates frozen + measured-fail report (`test_eval_model.py`) |
| 12 | Malformed Laya output fails closed (error/timeout/missing/invalid choice/probability/overflow) | `test_inv12_laya_timeout_falls_back_to_policy`, `test_laya_schema_battery.py`, `test_resilience.py` |
| 13 | Option/token budget violations handled explicitly | option-budget checks in `_validate_distribution`, frozen question counts (`test_questions_schema_frozen`) |
| 14 | No score questions for MVP (choice/noul only) | `QUESTIONS` has no score type; `test_questions_schema_frozen` |
| 15 | What-If Laya runs never write live audit; isolated cache namespace | `test_what_if_uses_isolated_laya_cache`, `test_what_if_second_emergency_leaves_no_trace`, dry-run rejection |
| 16 | Incident text is untrusted; bounded copy only, never instructions | `test_notes_never_reach_state_or_render`, `test_adversarial_free_text_is_cleaned_and_bounded`, `test_adversarial_notes_flagged_not_followed` |

## Matched rules (15)

| Rule ID | Fires when |
|---|---|
| `R-INPUT-REJECT-01` | hard-invalid input (Inv 1) → `REJECTED_INPUT` |
| `R-MODEL-FAILURE-HOLD-01` | severity/traffic status ≠ ok or anomaly model failed (Inv 4) → `MODEL_DEGRADED` |
| `R-DATA-QUALITY-HOLD-01` | data-quality anomaly (Inv 2) → `HOLD_FOR_HUMAN`, CRITICAL downgraded |
| `R-LOW-CONFIDENCE-HOLD-01` | `overall_confidence < 0.6` (§5.8) → `HOLD_FOR_HUMAN` |
| `R-INV-5-CRITICAL-NEEDS-TWO-SIGNALS-01` | CRITICAL requested with < 2 independent signals (Inv 5) → blocked |
| `R-LAYA-CRITICAL-BLOCKED-INSUFFICIENT-SIGNALS-01` | Laya suggests CRITICAL, signals insufficient (Inv 10) → blocked |
| `R-LAYA-LOW-ANSWER-CONFIDENCE-01` | Laya `answer_confidence < 0.5` → `HOLD_FOR_HUMAN` |
| `R-LAYA-HUMAN-REVIEW-SUGGESTED-01` | Laya `needs_human_review` true → `HOLD_FOR_HUMAN` |
| `R-LAYA-FALLBACK-POLICY-ONLY-01` | Laya degraded/invalid/timeout (Inv 12) → policy-only decision |
| `R-LAYA-MODEL-DEGRADED-01` | Laya status not ok but policy operating → `MODEL_DEGRADED` state marker |
| `R-CONTENTION-ESCALATE-01` | required resources unavailable → `CONTENTION_ESCALATION` (no fake success) |
| `R-TRUST-DOWNWEIGHT-01` | mean stream veracity < 0.7 (enhancement 1 trust scoring) → priority stepped down one level; flagged fake sources named in the reason |
| `R-EQUITY-UNSERVED-01` | E2 position = EQUITY and incident zone is underserved → priority raised one step (step-up recorded as the matched rule) |
| `R-ECO-ELECTRIC-FIRST-01` | E2 position = ECO → allocation picks the candidate with the highest `eco_score` (electric-first) |
| `R-AUTO-APPROVE-01` | all gates pass → `AUTO_APPROVED` (source `laya_proposed` iff Laya matched, else `policy_finalized`) |

## Guardrail precedence (order `decide()` applies)

`REJECTED_INPUT` → `MODEL_DEGRADED` (upstream ML) → `HOLD_FOR_HUMAN` (DQ / low
overall / low Laya AC / review suggestion) → `MODEL_DEGRADED` (Laya-only) →
`CONTENTION_ESCALATION` → `AUTO_APPROVED` (with `OVERRIDE_ACTIVE` possible later via
operator override on any decidable record).

## Override friction (enhancement 4 — server-classified tiers)

Friction is applied **after** the guardrail, at the override API, and never lets a
client bypass it: the server re-classifies each override into an impact tier and
rejects missing acknowledgements with 422.

| Tier | When | Required (else 422) |
|---|---|---|
| `LOW` | non-priority-changing, non-life-safety overrides | `operator_id` + `reason` only (Invariant 7) |
| `HIGH` | priority changes / dismissals on open incidents | + `impact_ack=true` + `context_code` |
| `BREAK_GLASS` | life-safety priority raises (e.g. dismissing a CRITICAL fire) | + `break_glass=true` |

`new_priority` is honored only for `CHANGE_PRIORITY` — stray values are normalized to
`None` client- and server-side so they can never escalate the tier. Tier, `context_code`
and `break_glass` are stored on the override record and its audit entry; a re-override
of an already-overridden decision is itself BREAK_GLASS. Evidence:
`tests/jevcity/test_friction.py`.

## Plan §6 six scenarios → tests (in `test_guardrail_invariants.py` unless noted)

1. Laya CRITICAL with one supporting signal → blocked: `test_inv10_laya_alone_cannot_force_critical`
2. AUTO_APPROVED low answer confidence → HOLD: `test_laya_low_answer_confidence_holds`
3. Laya ignores a data-quality anomaly → guardrail overrides: `test_plan6_laya_ignores_dq_anomaly_guardrail_overrides`
4. Laya recommends an unavailable resource → allocator corrects (escalates, no fake success): `test_plan6_laya_unavailable_resource_allocator_escalates` (+ `test_allocation.py`)
5. Laya contradicts the rules → rules win: `test_inv5_*`, `test_inv9_laya_invalid_fails_closed`
6. Laya proposes action from adversarial text → policy ignores text: `test_notes_never_reach_state_or_render`, `test_adversarial_notes_flagged_not_followed` (`test_simulation.py`)

## Confidence gates (§5.8 dual-gate)

- `OVERALL_GATE = 0.6` on `overall_confidence` (severity/traffic/DQ only — Laya excluded).
- `LAYA_ANSWER_CONFIDENCE_GATE = 0.5` on derived `answer_confidence`.
- Details + measured calibration: [`CONFIDENCE_CALIBRATION.md`](CONFIDENCE_CALIBRATION.md).
