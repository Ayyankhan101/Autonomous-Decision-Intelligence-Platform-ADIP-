# Phase 6 — Integration, Testing & Documentation (plan §Phase 6)

Source: `JevCity_Implementation_Plan_Revised_v2_Laya.docx` Phase 6 (weeks 9–10),
`docs/jevcity/PHASE0_SIGNOFF.md` (Gate 1 ✅, 22/22), plan §12 items 17/28 (model cards,
question schema version, limitations, guardrail design), plan §6 test categories.
Branch: `stage/phase6-integration-docs`. Execution: in-session.

## Current State (Phases 0–5 Shipped)

- **0–1**: seeded simulation, deterministic replay, ingestion validation & correlation,
  multi-report contradiction, bad-data injection, 16-invariant guardrail, append-only audit.
- **2**: real ML triad (`sev-gb-1.0.0`, `traffic-gbr-1.0.0`, `anom-ml-1.0.0`), calibrated
  overall confidence, latency measurement, timeout/error fallback (wrapper).
- **3**: in-process laya-mlx LIVE mode (10 s thread timeout, retry ×2, breaker 3/probe 5,
  fail-closed), state builder Inv-16, decision sources.
- **4**: audit Laya metadata complete, payload-hash chain stable, JSONL export CLI.
- **5**: dashboard (map/inspector/override/audit/What-If), `LayaBlock.distribution`,
  CI dashboard build. Suite **197 passed / 4 deselected**, ruff + oxlint green.

## What already covers plan §6 (audit 2026-10-07)

| Plan §6 item | Existing evidence |
|---|---|
| Bad-data regression (flag, not silently act) | `test_simulation.py` (hard reject, adversarial notes), Inv 1/2 |
| Contention test | `test_allocation.py` (contention escalation, not false success) |
| What-If isolation | `test_whatif.py` (5 tests: no audit, no mutation, isolated cache, rollback) |
| Deterministic replay | `test_replay.py` (9 tests) + seed determinism + cache-key determinism |
| Audit append-only | `test_audit.py` (triggers, chain, tamper detect, dry-run block) |
| Model-failure → human review | `test_guardrail_invariants.py` Inv 4 (parametrized status), wrapper fail-closed |
| Laya timeout / unreachable / fail-closed | `test_laya_adapter.py`, `test_resilience.py` |
| Laya schema (invalid priority, frozen questions) | `test_laya_adapter.py` normalize + `test_questions_schema_frozen` |
| Guardrail: CRITICAL needs ≥2 signals; low AC → HOLD; rules beat Laya; adversarial text ignored | Inv 5/10, `test_laya_low_answer_confidence_holds`, Inv 16, `test_adversarial_notes_flagged_not_followed` |
| End-to-end demo seed test | seeded determinism tests (per-surface), **not one single pass** → F1 |
| Latency behavior on exceed (fallback + degraded + audit) | pieces exist separately → F4 composite |

## Tasks

### F1: E2E one-pass integration test
`tests/jevcity/test_e2e_pipeline.py` — one test (or tight group): replay recording
(`datasets/jevcity/sim-session-v1.jsonl`) → live injected event → ML triad → Laya (mock,
deterministic) → guardrail finalization → dashboard payloads (`/api/state`, incidents,
decisions, resources) → audit entry present, hash-chained, carrying Laya metadata —
asserted in a single pass.

### F2: Laya response-schema / failure battery
`tests/jevcity/test_laya_schema_battery.py` — consolidate/extend: missing answers dict,
missing individual answers, invalid priority (already covered — keep local coverage),
negative probability, extra unknown fields ignored, empty response, malformed upstream
shape, probability-sum normalization, question-type + option-budget frozen assertions.
HTTP-sidecar-only failure modes (malformed JSON, checkpoint download, OOM, invalid
device) documented as in-process N/A in F8 rather than faked.

### F3: Guardrail scenario battery (plan §6 six scenarios)
Add the two missing scenarios to `test_guardrail_invariants.py`:
(a) Laya ignores a data-quality anomaly → guardrail overrides; (b) Laya recommends an
unavailable resource → allocator corrects/escalates. Map all six in docstring.

### F4: Composite degradation test (plan §6 latency budget behavior)
One test: forced Laya timeout **> budget** → (1) fallback decision still produced
(no crash), (2) `/api/state.last_laya_status` marks degraded/timeout, (3) audit entry
records the timeout with Laya metadata. All three surfaces in one test.

### F5: Event-pipeline load/latency check
`benchmarks/jevcity_pipeline_bench.py` — N inject→decision cycles, P50/P95 decision
latency vs plan budgets (§5 demo < 250 ms, §6 CPU < 750 ms), writes
`benchmarks/results/jevcity-pipeline-<host>-<ts>.json`, exit 1 over budget.

### F6: Model card + checkpoint card
`docs/jevcity/LAYA_MODEL_CARD.md` (purpose, inputs/outputs, training provenance pointer,
intended use, out-of-scope, measured eval + C4 fail honestly, limitations) and
`docs/jevcity/CHECKPOINT_CARD.md` (`aac6fef/laya-typed-decisions-mlx`, float16, cache
path, device/dtype, determinism key, license/provenance pointer, offline story).

### F7: Question templates, state builder, calibration docs
`docs/jevcity/LAYA_QUESTIONS.md` (q-0.1.0, three questions, criteria, option budgets,
no-score-question Invariant 14, hash), `docs/jevcity/STATE_BUILDER.md` (fields, bounds,
free-text cleaning, hashing — links ARCHITECTURE §State builder), and
`docs/jevcity/CONFIDENCE_CALIBRATION.md` (ERRATA C2/C3 derivation, dual gates 0.6/0.5,
C4 frozen-measured fail, honesty contract).

### F8: Guardrail + failure-mode docs
`docs/jevcity/GUARDRAIL.md` (16 invariants, 12 matched rules, precedence order, six
plan §6 scenarios → test map) and `docs/jevcity/LAYA_FAILURE_MODES.md` (timeout,
unreachable, breaker, empty/malformed, invalid choice, fail-closed ladder mock → cache
→ rules → HOLD; in-process N/A notes for sidecar-only modes; degraded UX surfaces).

### F9: Professional-practices write-up
`docs/jevcity/PROFESSIONAL_PRACTICES.md` — fairness (synthetic data, no protected
attributes used in features; scope limits), accountability (operator_id overrides, hash
chain, frozen routes), human oversight (HOLD_FOR_HUMAN, review suggestion, override
modal, dashboard divergence alerts), privacy (no raw free text to Laya, Inv 16,
redaction not needed for synthetic data — honest scope), limitations (C4 fail,
uncalibrated confidence, single checkpoint, synthetic-only incidents). Each claim tied
to implemented control + test.

### F10: Wiring & verification
README + ARCHITECTURE links to new docs; tests-map rows; plan status; full suite + ruff
+ dashboard lint/build; PR → CI → rebase-merge → post-merge CI → ledger.

## Deviations (carried from plan-of-record)

1. HTTP-sidecar Laya failure modes (malformed JSON, checkpoint download failure, OOM,
   invalid device) → in-process equivalent paths tested where they exist; the rest
   documented N/A in `LAYA_FAILURE_MODES.md` (ERRATA C1).
2. Fairness metrics: no protected attributes exist in the synthetic incident schema —
   write-up states the absence + what would be needed, no fake fairness numbers.

## Status (2026-10-08)

All tasks done on `stage/phase6-integration-docs`:

- F1 `tests/jevcity/test_e2e_pipeline.py::test_replay_history_then_live_event_one_pass` — found + fixed real bug: injected incident ids restarted at `inc-00001` after recording replay and silently merged into unrelated recorded incidents (`SimulationState._next_unique_incident_id`).
- F2 `tests/jevcity/test_laya_schema_battery.py` (21 cases) + normalize tightening: negative/out-of-range probabilities, probability-sum range, unknown option keys now fail closed (Inv 12/13).
- F3 two missing plan §6 scenarios added to `test_guardrail_invariants.py` (+ docstring map of all six).
- F4 `test_laya_timeout_degradation_composite` — fallback decision + `last_laya_status="timeout"` + audit timeout metadata in one test.
- F5 `benchmarks/jevcity_pipeline_bench.py` — p95 7.0 ms/20 events vs 250 ms demo budget (result stored); README section added.
- F6–F9 docs written: LAYA_MODEL_CARD, CHECKPOINT_CARD, LAYA_QUESTIONS, STATE_BUILDER, CONFIDENCE_CALIBRATION, GUARDRAIL (16 invariants + 12 rules + precedence + scenario map), LAYA_FAILURE_MODES, PROFESSIONAL_PRACTICES.
- F10 wiring: README docs list, ARCHITECTURE tests-map rows, schema export fresh (no drift).

Verification: ruff clean · suite **218 passed / 4 deselected** (was 197) · `pytest -m laya_live` 2 passed (tightened normalize validated against real checkpoint output) · oxlint clean · `pnpm build` clean.
