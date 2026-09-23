# Golden Set — Support-Ticket Triage v1

The frozen evaluation dataset for ADIP's flagship triage use case
(blueprint §9). **The labels in a frozen version are never edited** — errors
are corrected by publishing a new version with a changelog entry, so eval
results stay comparable across runs.

This set covers the **ticket-triage** question set only. Developer-workflow
domains from blueprint §5.1 (bug/issue triage, PR routing, incident response)
get their own directories here (e.g. `datasets/bug-triage/`) with the same
schema, guidelines, validator, and freeze discipline.

## What the model is asked (must match the serving config exactly)

```python
QUESTIONS = {
  "department": {"type": "choice",
                 "criteria": ["billing", "technical", "sales", "account"]},
  "urgency":    {"type": "score", "criteria": ["not urgent", "soon", "critical"]},
  "refund":     {"type": "noul",
                 "instructions": "Does the customer ask for money back?"},
}
```

The eval harness sends `text` as state and these questions (the canonical,
verbose form is stored in `golden-template.json -> question_set` and must
byte-match `evals/run_eval.py -> QUESTIONS`; the runner hard-fails on drift); predictions are
compared to `labels`. Changing the question set or option list = new dataset
major version.

## Files

| File | Purpose |
|---|---|
| `schema.json` | JSON Schema contract; every record validates against it |
| `guidelines.md` | Labeling rubric, decision trees, QC, and hard-case catalogue |
| `exemplars.json` | 5 fully-worked examples (one per label area + one hard case) |
| `golden-template.json` | Working file, now filled with all 50 (frozen copy: `golden-v1.0.json`) |
| `validate.py` | Schema + rubric cross-checks; run before freezing |

## Composition targets for v1 (50 tickets)

| Slot | Count | Rationale |
|---|---|---|
| billing / technical / sales / account | 15 / 15 / 8 / 12 | `account` and `sales` need enough mass for per-class metrics |
| urgency 0 / 1 / 2 | 20 / 18 / 12 | plenty of "not urgent" so `critical` is informative |
| refund = true | 15 | ~30%; includes 2 "money-adjacent but NOT refund" traps |
| language: en / other | 44 / 6 | 6 multilingual tickets to exercise Router evidence logging |
| hard cases (guidelines §6) | ≥ 8 | mandatory; tagged `meta.hard_case: true` |

## Workflow

1. Write tickets into `golden-template.json` following `guidelines.md`.
2. Run `python3 datasets/golden-set/validate.py --file datasets/golden-set/golden-template.json`.
3. Second labeler QC pass on all `confident: false` + 20% random sample;
   disagreements reconciled per guidelines §5 and marked `disagreement: true`.
4. Copy to `golden-v1.0.json`, update the changelog below, commit. **Frozen.**

## Changelog

| Version | Date | Records | Change |
|---|---|---|---|
| (unreleased) | — | 5 exemplars in template | structure + guidelines drafted |
| v1.0-rc1 | 2026-09-23 | 50 | TICKET-0006..0050 drafted (labeler `AI-1`) to the exact composition targets; strict validation passing. **RC, not final:** 45 labels are AI-drafted pending the §5 human QC pass (2 records already carry `second_labeler`). Eval baseline on this version: `evals/results/eval-AppleM1Pro-20260923T155249.json` — macro-F1 0.712, gates FAIL, recorded honestly. Labels change only via a new version after QC. |
| v1.0 | 2026-09-23 | 50 | **Frozen.** AI-2 second-labeler pass per §5: both `confident: false` records + a seeded 20% sample (11 records total) re-derived from the rubric — **zero label changes**; `second_labeler` recorded on each. Same question set as rc1 (hash `b580734fdd0c`), so eval numbers carry over: macro-F1 0.712, gates FAIL (`evals/results/eval-AppleM1Pro-20260923T174320.json`). Human sign-off still recommended before external quoting. |
