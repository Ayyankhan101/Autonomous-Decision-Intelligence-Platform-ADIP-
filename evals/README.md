# ADIP Eval Runner

Scores laya-mlx predictions against the frozen golden set
(`datasets/golden-set/`) — blueprint §9's nightly eval tier. Dependency-free
metrics, validated by `--selftest` against hand-computed cases.

**Scope:** the metrics are domain-agnostic (`choice` → F1/ECE/confusion,
`score` → level accuracy, `noul` → ECE/Brier). Ticket triage is the first
instance; bug/issue triage, PR routing, and incident response (blueprint §5.1)
extend the same runner with their own canonical `QUESTIONS` and gates — the
drift guard hard-fails a dataset whose question set doesn't match, which is
the feature, not a limitation.

```bash
python3 evals/run_eval.py --selftest
.venv-bench/bin/python evals/run_eval.py --file datasets/golden-set/golden-template.json
.venv-bench/bin/python evals/run_eval.py --file datasets/golden-set/golden-v1.0.json --strict
```

## Metrics

| Label | Metrics |
|---|---|
| `department` (choice) | macro-F1 (classes present in y_true) + per-class P/R/F1, accuracy, multiclass Brier, ECE(15) on selected-option probability, 4×4 confusion matrix |
| `urgency` (score) | accuracy of rounded expected score, ECE on the predicted level's probability mass |
| `refund` (noul) | accuracy @ 0.5, ECE(15), binary Brier on P(true) |

Every run: 2 full passes — determinism (per-record answers compared across
passes) and per-decision latency summary. Reports land in
`evals/results/eval-<chip>-<timestamp>.json`.

**Caveat written into every report:** the runner never edits the golden set.
If the question set in the dataset drifts from the runner's canonical
`QUESTIONS`, the run hard-fails instead of measuring the wrong task.

## Gates (`--strict`, blueprint §9)

| Gate | Threshold |
|---|---|
| macro-F1 | ≥ 0.85 |
| department ECE | < 0.05 |
| refund ECE | < 0.05 |
| determinism | passes identical |
| latency P95 | < 60 ms per decision |

## Status

- **2026-09-23 — smoke run on the 5 frozen exemplars** (M1 Pro, FP16, b=16):
  department acc 0.80 (missed the H2-style account-lockout ticket → predicted
  `technical` — the exact hard case the catalogue warns about), refund 0.80,
  urgency 0.40, deterministic ✓, p50 87 ms. Report:
  `evals/results/eval-AppleM1Pro-20260923T150442.json`.
  **This is a 5-record smoke run, NOT evidence about model quality** — ECE and
  F1 on n=5 carry no signal. Strict gates activate once the 50-ticket set is
  filled and frozen.

- **2026-09-23 — full strict eval on `golden-v1.0-rc1.json` (50 tickets)**
  (M1 Pro, FP16, b=16, 2 passes, report
  `evals/results/eval-AppleM1Pro-20260923T155249.json`, console log
  `evals/results/eval-v1.0-rc1-20260923.txt`). **Gates: FAIL** — recorded
  honestly, this is the baseline to improve from:

  | Metric | Result | Gate | Verdict |
  |---|---:|---|---|
  | department macro-F1 | 0.712 (acc 0.74) | ≥ 0.85 | ❌ |
  | department ECE | 0.202 | < 0.05 | ❌ |
  | refund ECE | 0.689 (acc 0.96) | < 0.05 | ❌ |
  | urgency accuracy | 0.48 (ECE-mass 0.163) | (no gate v1) | — |
  | determinism | 2/2 passes identical | identical | ✅ |
  | latency P95 | ~80+ ms (p50 80.0, max 237) | < 60 ms | ❌ |

  Confusion signal: `account` recall 0.50 — 6 of 12 lost, split 3×→billing,
  3×→technical; `sales` recall 0.50 (3×→technical); `billing` and
  `technical` hold ≥ 0.87 recall. The pre-registered hard-case traps behaved
  as predicted (e.g. account-vs-technical security/migration cases).
  **Caveats:** (1) 45 of 50 labels are AI-drafted pending human QC — treat
  as provisional until a second labeler reviews; (2) refund ECE is badly
  miscalibrated despite 0.96 accuracy (probabilities near-extreme but not
  ordered) — expected for the base checkpoint per the clamping warning;
  calibration tuning is the Phase-1 lever, not more labels; (3) latency
  includes full-ticket texts on this M1 Pro — batched short-state serving
  measured 61.6 ms p50 in `benchmarks/` (payload v2).

- **2026-09-23 — full strict eval on `golden-v1.0.json` (50 tickets, FROZEN v1.0)**
  (M1 Pro, FP16, b=16, 2 passes, payload v2 / question-set hash `b580734fdd0c`,
  report `evals/results/eval-AppleM1Pro-20260923T174320.json`, console log
  `evals/results/eval-v1.0-final-20260923.txt`). **Gates: FAIL** — same
  baseline, now against the frozen v1.0 set:

  | Metric | Result | Gate | Verdict |
  |---|---:|---|---|
  | department macro-F1 | 0.712 (acc 0.74) | ≥ 0.85 | ❌ |
  | department ECE | 0.202 | < 0.05 | ❌ |
  | refund ECE | 0.689 (acc 0.96) | < 0.05 | ❌ |
  | urgency accuracy | 0.48 (ECE-mass 0.163) | (no gate v1) | — |
  | determinism | 2/2 passes identical | identical | ✅ |
  | latency P95 | ~80+ ms on full tickets (p50 79.3, max 164) | < 60 ms | ❌ |

  Metrics are identical to the rc1 run — expected: the engine is deterministic
  and the AI-2 second-labeler pass (guidelines §5: 2 unconfident records + a
  20% sample) changed **zero labels**, so rc1 and v1.0 measure the same task.
  Labels are now AI-1 drafted + AI-2 verified; **human sign-off is still
  recommended before quoting these numbers externally.** Remaining levers,
  in order of expected yield: calibration tuning for the refund ECE, criteria
  rewording for the account/sales recall misses, M3 Max-class nodes or async
  probes for the latency gate.

## Found-and-fixed while building

- The runner's initial canonical QUESTIONS omitted `account` from the
  department criteria — 12 of the 50 planned golden tickets could never have
  been predicted correctly. Caught during the first real predict() probe;
  fixed in both the runner and the golden template's `question_set`.
