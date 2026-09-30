# JevCity Architecture (plan Rev 2, repo-aligned)

## Pipeline (vertical slice)

```
simulation (seeded clock + events)
  → ingestion.validate            [validation point 1: hard reject / soft flag]
  → ingestion.correlate           [incident_id correlation, contradictions]
  → features.engineer             [simulated-time features]
  → models (severity | traffic | anomaly stubs)
  → validation of outputs         [validation point 2: status != ok → fail closed]
  → laya_adapter (mock|cache|live-unavailable)
  → guardrail.policy.decide       [validation point 3: invariants final authority]
  → allocate (greedy) → decision record → audit (append-only)
```

Six core processing agents + governance/presentation per plan §3:
simulation, preprocessing/features, severity, traffic, anomaly, **decision engine**
(= Laya adapter + policy guardrail); human override & audit; command-center API.

## Decision authority

Laya **proposes**, deterministic policy **decides**. Priority comes from the three
upstream models only (Invariant 5/10); Laya may suggest, hold, and recommend resources —
never finalize. `laya.suggested_priority` is always recorded separately from final
`priority` (Key Rule §3.1.3). `final_decision_source` ∈ {laya_proposed, policy_finalized,
fallback_rule, human_required}.

Guardrail order: hard reject → model failure → signal combination (2-signal CRITICAL rule)
→ Laya advisory handling → data-quality hold → confidence gates → allocation → record.

## Confidence gates (§5.8)

```
overall_confidence = min(severity_confidence, traffic_confidence, 1 - data_quality_score)
AUTO eligible only if overall_confidence >= 0.6            # OVERALL_GATE
                    AND laya answer_confidence >= 0.5      # LAYA_ANSWER_CONFIDENCE_GATE (separate!)
```

Laya's `answer_confidence` is **never** folded into the min() (§5.8 correction).
Both numbers are **uncalibrated** until JevCity-fixture temperature fitting (ERRATA C3,
Invariant 11). Interim thresholds are demo defaults, not calibration claims.

## Laya state builder

Compact, decision-relevant fields only (LayaState schema): incident identity + zone +
simulated time + weather/traffic context + bounded attributes (vehicles/injuries/lanes)
+ model outputs with confidence + data-quality score/reasons + resource availability +
competing incidents count. Free-text `notes` **never** enters the state — handled by
anomaly/validator as data (Invariant 16). State and questions are sha256-hashed;
cache key = `state_hash + questions_hash + checkpoint + device + dtype` (Phase 0 item 20).

`answer_confidence` derivation (ERRATA C2): top-of-distribution probability from the
normalized response; raw upstream field unverified until Phase 3.

## Seeding & determinism

`SeedConfig(session_seed=42, scenario_seed=7)` → two `random.Random` streams
(`simulation/seeds.py`). Same seeds reproduce event order, attributes, injection modes,
resource states. SimClock epoch = 2026-09-27T10:00Z; **no host wall-clock anywhere** in
feature/decision timestamps.

## Decision states (6 — ERRATA C6)

`AUTO_APPROVED · HOLD_FOR_HUMAN · REJECTED_INPUT · CONTENTION_ESCALATION ·
OVERRIDE_ACTIVE · MODEL_DEGRADED`

Laya reason codes (accompany states): `LAYA_TIMEOUT, LAYA_INVALID_RESPONSE,
LAYA_LOW_ANSWER_CONFIDENCE, LAYA_SUGGESTION_BLOCKED_BY_POLICY, LAYA_FALLBACK_POLICY_ONLY`.

## Signal independence (Invariant 10 + ERRATA C5)

Eligible for the 2-signal CRITICAL rule: `severity_model`, `traffic_impact_model`,
`situational_anomaly_model`. Heuristic/threshold implementations **count** when they are
separately implemented + versioned (traffic-heuristic-0.1.0, anom-threshold-0.1.0).
Ineligible: Laya output/rationale, raw incident text, operator suggestion pre-override.

## Audit (Phase 4)

SQLite `audit_log`: INSERT-only via triggers (UPDATE/DELETE → `RAISE(ABORT)`), hash-linked
`previous_hash`/`entry_hash`, `validate_chain()` detects DB-level tampering. Every decision
emits an entry with actor/action/reason/timestamp/before-after/decision id/policy version/
model versions + full Laya metadata block (§3.1.4). Overrides require operator_id + reason
(Invariant 7). `dry_run` entries are rejected at the API (Invariant 15).

## What-If

Sandboxed `run_what_if`: deepcopy resource pool, fresh isolated Laya cache, no audit
append, no decision persistence, `dry_run=True` stamped on the decision. Predefined
scenarios only (remove_one_ambulance, close_road, second_emergency); second-emergency
sandbox incident is rolled back from the live registry on completion.

## Tests map (plan §6 gates)

| Gate | File |
|------|------|
| Invariants 1–5, 9–12, dual-confidence | `tests/jevcity/test_guardrail_invariants.py` |
| Seeding, clock, correlation, adversarial notes | `tests/jevcity/test_simulation.py` |
| Allocation / contention | `tests/jevcity/test_allocation.py` |
| Audit append-only + hash chain + dry-run block | `tests/jevcity/test_audit.py` |
| Adapter determinism/cache/fail-closed | `tests/jevcity/test_laya_adapter.py` |
| What-If isolation (Inv 6/15) | `tests/jevcity/test_whatif.py` |
| API contracts, override 422s | `tests/jevcity/test_api.py` |
| Schema freeze | `tests/jevcity/test_schemas.py` |

## Repo coexistence

- Triage platform (`adip/`, `serving/` port 8100, `evals/`, `benchmarks/`) untouched.
- JevCity API = port **8200** (`jevcity/api/app.py`).
- Runtime evidence reused: laya-mlx latency/calibration artifacts cited in
  `PHASE0_SIGNOFF.md`; live integration remains Phase 3 (adapter fails closed today).

## ML models (Phase 2)

| Model | Version | Method | Labels | Confidence / uncertainty |
|-------|---------|--------|--------|--------------------------|
| severity_predictor | sev-gb-1.0.0 | GradientBoosting + CalibratedClassifierCV (sigmoid) | hint mapping (minor→LOW, moderate→MEDIUM, severe→HIGH, severe+injuries≥2→CRITICAL) | calibrated P(predicted class) |
| traffic_impact_predictor | traffic-gbr-1.0.0 | GradientBoostingRegressor + quantile (0.1/0.9) | approved heuristic `traffic_delta` (sign-off item 3, ERRATA C5) | `confidence = 1 − (p90 − p10)` interval width |
| anomaly_detector | anom-ml-1.0.0 | LogisticRegression (data-quality) + IsolationForest (situational) | `quality_hints.injection_mode` present → dq_label=1 | `data_quality_score = P(bad)`; hard_rejected → forced 1.0 |

Shared: fixed-order encoder `jevcity/models/encode.py`, dataset `datasets/jevcity/ml/dataset.jsonl` (split `i % 5 == 0` held-out), wrapper `jevcity/models/wrapper.py` (timeout 0.5 s → TIMEOUT / fail-closed anomaly, exceptions → ERROR, measured latency), metrics `evals/eval_ml.py` → `evals/results/ml-phase2-v1.json`. Laya state carries `severity_model_version` + `traffic_model_version`; `overall_confidence` §5.8 min() unchanged (Laya excluded).

## CI / repo protection

- `.github/workflows/ci.yml`: `lint + model-free tests` (ubuntu, PR + push, junit
  artifact on failure) → `strict eval (macos)` (main/dispatch only: model tier
  `model and not laya_live`, live smoke `laya_live`, C4 gate **warn + job-summary**
  while C4 open — flip step to hard-fail after Gate 1 closes). Least-privilege
  `permissions: contents: read`, per-ref concurrency cancel, job timeouts.
- Ruleset `main-protection` (id 24235972): block force-push + deletion, require
  check `lint + model-free tests` (non-strict). **Required check blocks all
  direct pushes to `main`** (a new head cannot carry checks yet) — therefore
  **all changes land via branch + PR** (rebase-merge keeps linear history; unit
  job runs on PRs; macOS job is main-only by design and is not required).
- `.github/dependabot.yml`: github-actions, monthly.
- Freshness guard: `tests/test_schemas_export.py` — `schemas/*.json` must match
  `uv run python -m jevcity.schemas.export` byte-for-byte.
