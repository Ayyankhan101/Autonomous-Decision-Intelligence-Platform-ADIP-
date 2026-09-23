# ADIP Eval Runner

Scores laya-mlx predictions against the frozen golden set
(`datasets/golden-set/`) — blueprint §9's nightly eval tier. Dependency-free
metrics, validated by `--selftest` against hand-computed cases.

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
| latency P50 | < 60 ms per decision |

## Status

- **2026-09-23 — smoke run on the 5 frozen exemplars** (M1 Pro, FP16, b=16):
  department acc 0.80 (missed the H2-style account-lockout ticket → predicted
  `technical` — the exact hard case the catalogue warns about), refund 0.80,
  urgency 0.40, deterministic ✓, p50 87 ms. Report:
  `evals/results/eval-AppleM1Pro-20260923T150442.json`.
  **This is a 5-record smoke run, NOT evidence about model quality** — ECE and
  F1 on n=5 carry no signal. Strict gates activate once the 50-ticket set is
  filled and frozen as `golden-v1.0.json`.

## Found-and-fixed while building

- The runner's initial canonical QUESTIONS omitted `account` from the
  department criteria — 12 of the 50 planned golden tickets could never have
  been predicted correctly. Caught during the first real predict() probe;
  fixed in both the runner and the golden template's `question_set`.
