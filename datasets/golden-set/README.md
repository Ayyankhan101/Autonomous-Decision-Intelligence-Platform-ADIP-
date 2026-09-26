# Golden Set — Support-Ticket Triage v2

The frozen evaluation dataset for ADIP's flagship triage use case
(blueprint §9). **The labels in a frozen version are never edited** — errors
are corrected by publishing a new version with a changelog entry, so eval
results stay comparable across runs. v2.0 changed only the question set
(sales criteria enriched to payload v3); labels are byte-identical to v1.0.

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
byte-match `adip.questions.QUESTIONS` — the runner hard-fails on drift via
`assert_matches()`); predictions are compared to `labels`. Changing the
question set or option list = new dataset major version (v1.0 → v2.0 did
exactly this: sales criteria, labels untouched).

## Files

| File | Purpose |
|---|---|
| `schema.json` | JSON Schema contract; every record validates against it |
| `guidelines.md` | Labeling rubric, decision trees, QC, and hard-case catalogue |
| `exemplars.json` | 5 fully-worked examples (one per label area + one hard case) |
| `golden-template.json` | Working file, filled with all 50 (frozen copies: `golden-v2.0.json` current, `golden-v1.0.json` historical) |
| `golden-v2.0.json` | the frozen set every eval run names (payload v3) |
| `golden-v1.0.json` | frozen labels v1.0 (payload v2 question set — kept for provenance; labels identical to v2.0) |
| `validate.py` | Schema + rubric cross-checks; run before freezing |
| `qc_sweep.py` | regex label-vs-text sweep; `--strict` exits 1 on unresolved must-flags |
| `qc-worksheet-v1.0.md` | human QC worksheet with sign-off box |

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
2. `uv run python datasets/golden-set/validate.py --file datasets/golden-set/golden-template.json --strict --expect 50`
   (`--expect` enforces record count; missing `records` key or any failed
   check = `SystemExit`, exit 1 — CI-usable).
3. Second labeler QC pass on all `confident: false` + 20% random sample;
   disagreements reconciled per guidelines §5 and marked `disagreement: true`.
4. `uv run python datasets/golden-set/qc_sweep.py --strict` (exit 1 if any
   must-flag is unresolved) + fill `qc-worksheet-v1.0.md`.
5. Copy to `golden-vX.Y.json` (major bump if `question_set` changed), update
   the changelog below, commit. **Frozen.**

## Changelog

| Version | Date | Records | Change |
|---|---|---|---|
| (unreleased) | — | 5 exemplars in template | structure + guidelines drafted |
| v1.0-rc1 | 2026-09-23 | 50 | TICKET-0006..0050 drafted (labeler `AI-1`) to the exact composition targets; strict validation passing. **RC, not final:** 45 labels are AI-drafted pending the §5 human QC pass (2 records already carry `second_labeler`). Eval baseline on this version: `evals/results/eval-AppleM1Pro-20260923T155249.json` — macro-F1 0.712, gates FAIL, recorded honestly. Labels change only via a new version after QC. |
| v1.0 | 2026-09-23 | 50 | **Frozen.** AI-2 second-labeler pass per §5: both `confident: false` records + a seeded 20% sample (11 records total) re-derived from the rubric — **zero label changes**; `second_labeler` recorded on each. Same question set as rc1 (hash `b580734fdd0c`), so eval numbers carry over: macro-F1 0.712, gates FAIL (`evals/results/eval-AppleM1Pro-20260923T174320.json`). Human sign-off still recommended before external quoting. |
| v1.0+AI-3 | 2026-09-23 | 50 | AI-3 systematic sweep added (`qc_sweep.py`): regex evidence checks of every label against the text — **0 must-flags, 12 verify items** (all expected non-English ownership-rule tie-breaks). 8 initial flags adjudicated against guidelines §2: all were regex under-matching ("refunded", "payments are blocked"), zero label defects; patterns fixed in the tool. Self-contained human QC worksheet: `qc-worksheet-v1.0.md` (sign-off box included; any amended label = cut v1.1 per freeze discipline). **v1.0 labels unchanged** — no re-freeze needed. |
| v2.0 | 2026-09-26 | 50 | **Question set change, labels untouched** (major bump per the rule above): `sales` criteria enriched from "new purchases, upgrades, pricing" to the rubric's full pre-purchase scope (`… discounts, roadmap questions, partner/reseller programs, pre-purchase evaluations and comparisons`), payload v2 → **v3**, question-set hash `b580734fdd0c` → `13393cd59b87`. Records byte-identical to v1.0 (`tests/test_dataset.py::test_v2_changed_questions_not_labels`). Effect: macro-F1 0.7117 → 0.7698 on this set. **Disclosure:** the wording was selected by probing payload variants against these same 50 tickets (in-sample; human sign-off + fresh holdout recommended before external quoting). Eval: `evals/results/eval-AppleM1Pro-20260926T073703.json` (9/9 gates PASS). |
