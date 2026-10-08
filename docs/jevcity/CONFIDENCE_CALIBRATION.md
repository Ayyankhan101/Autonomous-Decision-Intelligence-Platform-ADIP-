# Confidence Calibration

ERRATA C2/C3/C4 + plan §5.8 (dual-gate correction). This is the single wording
everywhere: **Laya confidence is uncalibrated until JevCity-fixture-measured.**

## Two numbers, two roles

| Number | Where | Role |
|---|---|---|
| `answer_confidence` | Laya answers — **derived** by `normalize.py` (top-of-distribution probability); upstream does not provide it (verified live Phase 3) | Gate only: `LAYA_ANSWER_CONFIDENCE_GATE = 0.5` — low AC → `HOLD_FOR_HUMAN` (`R-LAYA-LOW-ANSWER-CONFIDENCE-01`) |
| `overall_confidence` | Decision record — `guardrail/confidence.overall_confidence()` = min(severity conf, traffic conf, 1 − data-quality badness) — **excludes Laya structurally** | Gate: `OVERALL_GATE = 0.6` — low → `HOLD_FOR_HUMAN` (`R-LOW-CONFIDENCE-HOLD-01`) |

Laya is also **structurally ineligible** as an independent CRITICAL signal
(`critical_signal_count` has no Laya parameter — Invariant 10, tested
`test_laya_not_counted_as_independent_signal`).

`confidence` vs `answer_confidence` on a normalized answer: `confidence` = raw top
probability, `answer_confidence` = gated number (post temperature-fit when available,
else raw). Gates read `answer_confidence` only.

## Measured calibration (frozen gate, honest verdict)

Runner: `evals/run_jevcity_eval.py` on `fixtures/jevcity_decisions.jsonl`.

| | Measured | Gate (ERRATA C4, frozen) |
|---|---|---|
| Accuracy | 0.5675 (n = 84) | ≥ 0.70 |
| ECE | 0.3528 | ≤ 0.15 |

**Both gates FAIL.** CI (`macos` strict-eval job) reports the failure as a warning +
step summary — thresholds are frozen, never moved to go green. Honesty contract:
`tests/jevcity/test_eval_model.py` (runner must report measured values, no
self-grading); gate truth: `tests/jevcity/test_fixtures.py`.

## Interim controls while uncalibrated

1. Dual-gate design (§5.8): automation needs `overall_confidence ≥ 0.6` *and* Laya
   `answer_confidence ≥ 0.5` — neither alone approves.
2. CRITICAL requires ≥ 2 independent upstream signals; Laya never counts.
3. All confidence is `ge=0, le=1` schema-constrained; distribution sums validated
   (`_validate_distribution`).
4. Calibration work = checkpoint/label alignment tracked in `PHASE0_SIGNOFF.md`
   row 21 + risk table (the only open Gate-1 note).
