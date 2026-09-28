# JevCity Plan Errata — Rev 2 vs repo reality

Resolutions applied when altering this repo per `JevCity_Implementation_Plan_Revised_v2_Laya.docx`.
Decision rule (agreed): **plan + repo alignment** — where the plan document contradicts this
repository's measured evidence or itself, the resolution below wins.

| ID | Plan says | Conflict | Resolution |
|----|-----------|----------|------------|
| C1 | `pip install laya`, `laya[serve]` sidecar (`/v1/systemone`), `laya-evals` CLI, `predict_long`, GPU ~33 ms / CPU 193–464 ms/question | None of these are verified here. Repo runs **`laya-mlx==0.2.0`** (Apple MLX), measured M1 Pro **61.6–93.6 ms per 3-question decision** (`benchmarks/results/*.json`), own eval harness (`evals/run_eval.py`) | Runtime = laya-mlx, in-process. `laya-serve`, `/v1/systemone`, `laya-evals`, `predict_long` = **unverified claims**; adapter ships mock/cache modes, live mode is Phase 3 |
| C2 | Gate on `answer_confidence`; "Laya's documentation describes [it] as the single calibrated probability" | `answer_confidence` does not appear in this repo's Laya output contract (`BLUEPRINT` §4.1: `probability`, `distribution`, `expected_score`; derived `confidence`) | Normalizer **derives** `answer_confidence` from top-of-distribution probability; derivation documented in `jevcity/decision_engine/laya_adapter/normalize.py`. Upstream-field verification = open Phase 0 task (item 18) |
| C3 | §3.1.2: answer_confidence **is** calibrated · Invariant 11: overconfident as shipped · §5.8: needs its own calibration | Three contradictory statements | Single wording everywhere: **treat Laya confidence as uncalibrated until JevCity-fixture-measured.** §3.1.2 claim struck |
| C4 | Phase 2 gate `accuracy ≥ 0.75, ECE ≤ 0.10` vs Phase 6 gate `accuracy ≥ 0.70, ECE ≤ 0.12` | Two different gates, no reconciliation | One pair, one location: **interim `accuracy ≥ 0.70`, `max ECE ≤ 0.15`** (repo's own n=50 lesson: honest OOF ECE lands 0.13–0.17; bar moved 0.10→0.15 with evidence). Re-tune when JevCity fixtures exist |
| C5 | Invariant 5/10: CRITICAL needs 2 independent **model** signals; but Phase 0/2 allow rule-based traffic heuristic + threshold anomaly | If traffic = heuristic and anomaly = thresholds, only severity is a "model" → CRITICAL path dead | **Heuristic/threshold components count** as independent signals if separately implemented, versioned, and status=ok. Laya remains ineligible (Invariant 10) |
| C6 | §3.2 table lists 6 states incl. `MODEL_DEGRADED`; prose directly above says "No new states are needed for MVP" | Self-contradiction | **`MODEL_DEGRADED` is a valid state** (6 states). Prose was stale; table wins |
| C7 | Phase 0 exit = 22 items (§4) vs 6 items (§12) vs prose Gate 1 (§9.1) | Three inconsistent checklists | **One checklist = §4's 22 items**; §12's 5+1 folded into it as rows 1–5 (scope/docs rows) and row 12 (Laya integration). See `PHASE0_SIGNOFF.md` |

## Additional repo-alignment notes

- **Audit:** triage's `serving/audit.db` uses `INSERT OR REPLACE` (upsert, not append-only).
  JevCity audit = new INSERT-only table + `previous_hash`/`entry_hash` chain. Triage DB untouched.
- **Ports:** triage app `serving/app.py` = 8100; JevCity API = **8200** (separate app module).
- **Tests:** JevCity tests live under `tests/jevcity/` (repo's single pytest root), not `jevcity/tests/`.
  Plan's `schemas/` top-level intent satisfied by `jevcity/schemas/` (importable) + exported
  JSON Schema in `schemas/*.json` (frontend/dashboard contract).
- **Checkpoints:** plan's `laya`/`laya-typed-decisions` = upstream names; this repo pins
  `aac6fef/laya-typed-decisions-mlx` (see `BLUEPRINT.md`).
- **Python:** plan says 3.10+; repo requires **3.11+** (`pyproject.toml`), measured on 3.11/3.12.
- **`answer_confidence` derivation vs raw `confidence`:** both appear on normalized answers —
  `confidence` = raw top probability, `answer_confidence` = gated number (post temperature-fit
  when available, else raw). Difference documented; gates use `answer_confidence` only.
