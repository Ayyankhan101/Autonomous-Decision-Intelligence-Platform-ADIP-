# Golden Set — Support-Ticket Triage v1

The frozen evaluation dataset for ADIP's flagship triage use case
(blueprint §9). **The labels in a frozen version are never edited** — errors
are corrected by publishing a new version with a changelog entry, so eval
results stay comparable across runs.

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

The eval harness sends `text` as state and these questions; predictions are
compared to `labels`. Changing the question set or option list = new dataset
major version.

## Files

| File | Purpose |
|---|---|
| `schema.json` | JSON Schema contract; every record validates against it |
| `guidelines.md` | Labeling rubric, decision trees, QC, and hard-case catalogue |
| `exemplars.json` | 5 fully-worked examples (one per label area + one hard case) |
| `golden-template.json` | 50-slot file with 5 exemplars in place; 45 tickets to fill |
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
