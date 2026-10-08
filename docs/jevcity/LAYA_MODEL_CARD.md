# Laya Model Card — JevCity advisory decision model

Plan §Phase 6 ("Laya model card"), signoff item 28 (model card, question schema
version, limitations, guardrail design). Companion: [`CHECKPOINT_CARD.md`](CHECKPOINT_CARD.md),
[`CONFIDENCE_CALIBRATION.md`](CONFIDENCE_CALIBRATION.md), [`GUARDRAIL.md`](GUARDRAIL.md).

## Model details

| | |
|---|---|
| Purpose | Advisory triage of city incident decisions: priority, human-review need, recommended resource type |
| Runtime | `laya-mlx==0.2.0` (Apple MLX, in-process; ERRATA C1) |
| Checkpoint | `aac6fef/laya-typed-decisions-mlx` (see checkpoint card) |
| Router model | `typed-decisions` |
| Question schema | `QUESTIONS_VERSION = q-0.1.0` — `docs/jevcity/LAYA_QUESTIONS.md` |
| State contract | `jevcity/decision_engine/laya_adapter/state_builder.py` — `docs/jevcity/STATE_BUILDER.md` |
| Output contract | `NormalizedLayaResponse` (`jevcity/schemas/laya.py`), validated by `normalize.py` (fail closed, Invariant 12) |

## Intended use

- Advisory input to the JevCity guardrail. **Laya never has final authority**: every
  suggestion passes the rule-based policy (`decide()`), which can block, downgrade, or
  hold the result (`GUARDRAIL.md`).
- Three typed questions only (plan §3.1.1, Invariant 14: no score questions for MVP).
- Deterministic demo replay: mock mode answers are a pure function of state.

## Out-of-scope use

- Autonomous dispatch or actuation without guardrail approval.
- Any decision where Laya output is used without policy finalization (the API only
  exposes finalized decisions).
- Non-incident domains, other languages (English checkpoint; multilingual variant not
  pinned), or states outside `LayaState` (free text never reaches the model, Inv 16).

## Inputs and outputs

- Input: compact `LayaState` (incident fields + model outputs, bounded, hashed sha256)
  plus the frozen `QUESTIONS` payload.
- Output per question: choice/noul answer with distribution; `answer_confidence` is
  **derived** by the normalizer (top-of-distribution probability) — upstream does not
  provide it (ERRATA C2, verified live Phase 3). Treat as **uncalibrated** (ERRATA C3).
- On any validation failure: `LayaStatus.INVALID_RESPONSE`, `error_code` recorded,
  guardrail falls back to policy (fail closed).

## Evaluation

Fixture set: `fixtures/jevcity_decisions.jsonl` (n = 84, labels from the
baseline-proposer rubric), runner `evals/run_jevcity_eval.py`, honesty contract in
`tests/jevcity/test_eval_model.py`.

Measured (`evals/results/eval-jevcity-*.json`, latest):

| Metric | Measured | Gate (ERRATA C4, frozen) | Verdict |
|---|---|---|---|
| Accuracy | 0.5675 | ≥ 0.70 | **FAIL** |
| ECE | 0.3528 | ≤ 0.15 | **FAIL** |
| Determinism (repeats) | pass | exact repeat | pass |
| Priority accuracy | 0.6548 | — | reported |
| needs_human_review accuracy | 0.2857 | — | reported (weakest) |
| recommended_resource_type accuracy | 0.7619 | — | reported |

C4 gates are frozen and CI reports the failure as a warning + step summary — the
numbers above are never green-washed. Closing the gap = checkpoint/label alignment
work tracked in `PHASE0_SIGNOFF.md` row 21.

Latency (M1 Pro, `benchmarks/results/latency-AppleM1Pro-*.json`): 61.6–93.6 ms per
3-question decision — within plan budgets (§5 demo < 250 ms, §6 CPU < 750 ms).

## Limitations

1. Confidence is uncalibrated until fixture temperature fitting exists (ERRATA C3);
   the dual-gate design (`OVERALL_GATE = 0.6`, `LAYA_ANSWER_CONFIDENCE_GATE = 0.5`)
   is the interim control.
2. Measured accuracy below the frozen gate — advisory trust must stay bounded;
   guardrail rules, not Laya, carry the safety case.
3. `needs_human_review` accuracy is weak (0.2857) — its suggestion is treated as one
   input to policy holds, never as a sole authority either way.
4. Trained/fine-tuned upstream on synthetic decision tasks; JevCity incident states
   are themselves synthetic (seeded simulator). No real-city validation.
5. Single pinned checkpoint, single language, float16 (numerical parity story:
   BLUEPRINT §8.12).

## Fairness, oversight, privacy

See [`PROFESSIONAL_PRACTICES.md`](PROFESSIONAL_PRACTICES.md) — each claim there is
tied to an implemented control and its test.
