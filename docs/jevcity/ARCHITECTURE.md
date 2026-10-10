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

## Enhancements E1–E4 + demo-liveness

- **E1 trust scoring** — per-stream veracity from report history; mean veracity < 0.7
  fires `R-TRUST-DOWNWEIGHT-01` (priority stepped down one level, fake sources named).
  `POST /api/simulation/sybil` injects an honest seed + 2–10 fabricated reports for the
  demo (`test_trust.py`; rules table in `GUARDRAIL.md`).
- **E2 policy position sandbox** — runtime switch `RESPONSE_TIME | EQUITY | ECO`
  (`POST /api/policy/position`). New decisions follow the position; `reoptimise_active=true`
  re-decides open incidents (units released/reassigned) and emits `R-EQUITY-UNSERVED-01` /
  `R-ECO-ELECTRIC-FIRST-01` as matched rules. Writes `POLICY_POSITION_SWITCHED` audit
  entry **on the simulation clock**. Position is runtime config: persists across
  `/api/simulation/start` and `/reset` (only an explicit switch changes it) — pin it to
  reproduce seeded runs (`test_policy_sandbox.py`).
- **E3 decision lineage** — `GET /api/decisions/{id}` carries an optional `lineage` block
  (evidence terms, decisive clause, expression) for explainability demos (`test_lineage.py`).
- **E4 override friction** — server classifies each override into `LOW | HIGH | BREAK_GLASS`
  impact tiers; HIGH needs `impact_ack` + `context_code`, life-safety priority raises are
  BREAK_GLASS and need `break_glass=true` (missing → 422). `new_priority` is honored only
  for `CHANGE_PRIORITY` (stray values normalized away client- and server-side). Tiers +
  context stored on record and audit entry (`test_friction.py`).
- **Demo-liveness** — `GET /api/audit/verify` recomputes the full SHA-256 chain now
  (`{ok, entry_count, broken_at}`); `POST /api/simulation/laya-mode` hot-swaps the adapter
  mock|cache|live at runtime (live loads lazily, fail-closed routing unchanged).

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
normalized response; upstream `answer_confidence` verified **absent** from raw laya-mlx
output (Phase 3 C6 live contract test) — derivation is the contract.

## Laya LIVE mode (Phase 3)

`LayaAdapter(mode=LIVE)` runs the real in-process `laya_mlx` agent (checkpoint
`aac6fef/laya-typed-decisions-mlx`, float16). Call path per `ask()`:
breaker gate → retry (TimeoutError only, `LIVE_MAX_ATTEMPTS=2`) → predict on a daemon
thread with `LIVE_TIMEOUT_S=10.0` wall-clock → `to_raw` (C1 shape: answers carry
choice/probabilities/noul, **no** `answer_confidence`) → `normalize` (derivation +
state/questions hashes). Fail-closed: runtime error → `UNAVAILABLE`, overrun →
`TIMEOUT`, unextractable raw → `INVALID_RESPONSE`, all surfaced as
`MODEL_DEGRADED` policy-side (`FALLBACK_RULE`), never an auto-decision.

Circuit breaker: `LIVE_BREAKER_THRESHOLD=3` consecutive failures opens calls
(`error_code=circuit_open`, status `UNAVAILABLE`) with a half-open probe allowed
every `LIVE_BREAKER_PROBE_EVERY=5`th blocked call; success resets. Lazy agent load
(`_live_agent()` module cache) inside the timeout thread, so cold start cannot
blow the wall clock. `health()` probe reports mode/runtime/checkpoint/router_model/
device/dtype/live_agent_loaded/live_timeout_s/breaker_open.

Guardrail sources on LIVE outcomes (one explicit source per decision,
`LayaBlock.final_decision_source`): suggestion matches policy → `LAYA_PROPOSED`;
modified → `POLICY_FINALIZED`; Laya unavailable → `FALLBACK_RULE`; review/low-AC
hold or rejected input → `HUMAN_REQUIRED`. Every record stamps `policy_version`.

Free text (weather/traffic_level) is control-char-stripped and clamped to
64 chars in `build_state`; `render_state` is `key=<json>` lines, so payload
newlines cannot spoof structure (tests/jevcity/test_laya_adapter.py).

Tests: model-free live-path suite (`test_laya_adapter.py` fail-closed,
`test_resilience.py` retry+breaker, `test_decision_source.py` sources) + live
checkpoint smoke (`test_laya_live.py`, marks `model` + `laya_live`, CI step
"LayA live smoke" in the macos job).

## Seeding & determinism

`SeedConfig(session_seed=42, scenario_seed=7)` → two `random.Random` streams
(`simulation/seeds.py`). Same seeds reproduce event order, attributes, injection modes,
resource states. SimClock epoch = 2026-09-27T10:00Z; **no host wall-clock anywhere** in
feature/decision timestamps (every audit append passes the sim clock explicitly).

Determinism caveat (QA-verified): the E2 policy position is runtime config and persists
across start/reset — same seeds with a *different* position legitimately diverge.
Pin the position to reproduce; with it pinned, decisions are byte-identical across
process restarts.

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

**Read model:** `GET /api/audit?limit=100` returns entries **newest-first**;
every entry's `timestamp` is the simulation clock (`POLICY_POSITION_SWITCHED`
included — QA loop 2). The log is immutable by design: it survives an in-process
`/api/simulation/reset` (reset clears session state, not history) and is only
recreated by a process restart (default `:memory:` store).

**Operator identity:** `operator_id` = opaque non-empty string (no directory/authn in MVP);
actor `system` is reserved for engine-emitted entries. **Read-only guarantee:** the only
audit route is `GET /api/audit` (plus read-only `GET /api/audit/verify`) — no
PUT/PATCH/DELETE route exists (16 plan-frozen routes unchanged + 6 additive = 22,
ledger asserted in `tests/jevcity/test_audit_phase4.py`) and SQL triggers abort
mutations.

**Laya metadata** on both `DECISION_EMITTED` and `OVERRIDE_APPLIED` entries: checkpoint,
router model, status, state/questions hash, questions version (`q-0.1.0`), suggested
priority, answer confidence, latency, `guardrail_applied`, `final_decision_source`,
`fallback_used` (status != OK), `guardrail_modified` (source == POLICY_FINALIZED;
LAYA_PROPOSED → False, no suggestion → None).

**Hash stability:** `entry_hash` is computed over the stored payload JSON minus the hash
field itself (`payload_hash()`), so adding schema fields never invalidates old rows.

**Export:** `uv run python tools/export_audit.py [--db PATH] [--out FILE]` dumps JSONL
read-only (`mode=ro`), refusing `:memory:` and failing non-zero on a broken chain
(`jevcity/audit/export.py`). No new API endpoint beyond the 22-route ledger.

## What-If

Sandboxed `run_what_if`: predefined scenarios only (remove_one_ambulance, close_road,
second_emergency); results always carry `dry_run=true, audit_written=false,
live_state_mutated=false`. Isolation is enforced by `sandbox_scope()`
(`engine.py`): on entry it snapshots the simulation clock, fired-events set, generator
counters, both RNG stream states, resource pool, `_processed` cursor, decision/history/
validation collections, trust scores, engine `_counter`, and audit entry count —
restored on exit, so a dry-run cannot tick the live clock, consume incident ids, or
leave any residue (regression-tested by the residue assertions in
`test_edge_coverage.py`; `sandbox_store` keeps results keyed `sbx-*` for
`GET /api/what-if/{sandbox_id}/result`). Second-emergency's sandbox incident is also
rolled back from the live registry on completion. The Laya cache uses an isolated
namespace (Inv 6/15).

## Command Center dashboard (Phase 5)

React + TypeScript + Vite + Tailwind app in `dashboard/`, built to `dashboard/dist` and
served by the API at `/` (`StaticFiles` mount, skipped when `dist` is absent; `/api/*`
routes unaffected — the 16 frozen routes plus 6 additive are the full ledger). CORS middleware allows the Vite dev
origin (`:5173`/`:3000`, wildcard in dev). Data layer polls `/api/state`, `/api/incidents`,
`/api/decisions`, `/api/resources`, `/api/audit` every **1.5 s**.

**Views:** Command Center (5-zone map with severity-colored incident pins + fleet
availability bars, incident inspector, simulation controls), What-If sandbox, audit trail.

**Inspector split:** upstream ML triad signals → Laya advisory card (suggested priority,
answer confidence, probability distribution bars, status `laya_*`, checkpoint, router @
device, guardrail flag, latency, state hash) side-by-side with the deterministic policy
card (governed priority, decision state, final decision source, matched rules, structured
reasons); divergence banner when policy modifies Laya's suggestion. Advisory card has a
**display-only** hide/show toggle — no frozen endpoint can switch the adapter's runtime
mode; policy authority and audit are unaffected either way.

**Required UI states:** backend unreachable (banner + header badge), simulation paused
(header), model degraded (header `last_laya_status` badge + `MODEL_DEGRADED` state),
audit write failed / server error (5xx classified in the API client), What-If sandbox
expired (404 on stored-result re-fetch), contention alert (any `CONTENTION_ESCALATION`),
bad-data hold (hard-rejected incidents / `REJECTED_INPUT` decisions).

**Override + audit in UI:** Override modal enforces non-empty `operator_id` + `reason`
(Invariant 7), posts to the existing `POST /api/overrides`; audit tab renders actor,
action, before/after, full Laya metadata block, and entry/previous hashes (client display
only — chain validation itself is server-side: `validate_chain` / export CLI).

## Tests map (plan §6 gates)

| Gate | File |
|------|------|
| Invariants 1–5, 9–16, dual-confidence, plan §6 six guardrail scenarios | `tests/jevcity/test_guardrail_invariants.py` |
| Seeding, clock, correlation, adversarial notes | `tests/jevcity/test_simulation.py` |
| Allocation / contention | `tests/jevcity/test_allocation.py` |
| Audit append-only + hash chain + dry-run block | `tests/jevcity/test_audit.py` |
| Audit Phase 4: route freeze, original visible after override, Laya status/metadata auditable | `tests/jevcity/test_audit_phase4.py` |
| Audit export (JSONL, chain-validated, read-only) | `tests/jevcity/test_audit_export.py` |
| Adapter determinism/cache/fail-closed + injection resistance (Inv 16) | `tests/jevcity/test_laya_adapter.py` |
| Laya response-schema/failure battery (plan §6, Inv 12/13) | `tests/jevcity/test_laya_schema_battery.py` |
| LIVE retry + circuit breaker | `tests/jevcity/test_resilience.py` |
| Decision sources on LIVE path (Inv 7-adjacent) | `tests/jevcity/test_decision_source.py` |
| Live checkpoint contract smoke (C6; marks `model laya_live`) | `tests/jevcity/test_laya_live.py` |
| E2E one-pass (replay → live event → triad → Laya → guardrail → dashboard → audit) + latency-budget degradation composite | `tests/jevcity/test_e2e_pipeline.py` |
| What-If isolation (Inv 6/15) | `tests/jevcity/test_whatif.py` |
| API contracts, override 422s | `tests/jevcity/test_api.py` |
| Schema freeze | `tests/jevcity/test_schemas.py` |
| Phase 5 dashboard: CORS, static mount, frozen routes with dashboard, sim/override/What-If/bad-data flows | `tests/jevcity/test_dashboard_phase5.py` |
| `LayaBlock.distribution` plumbing on LIVE path | `tests/jevcity/test_laya_distribution.py` |
| Fixture honesty (C4 gates + measured fail report) | `tests/jevcity/test_fixtures.py`, `tests/jevcity/test_eval_model.py` |
| E1 trust scoring + Sybil flood | `tests/jevcity/test_trust.py` |
| E2 policy position switch, reoptimise + sim-clock audit | `tests/jevcity/test_policy_sandbox.py` |
| E3 decision lineage block | `tests/jevcity/test_lineage.py` |
| E4 override friction tiers, stray `new_priority` normalization | `tests/jevcity/test_friction.py` |
| Demo beats / CLI script | `tests/jevcity/test_demo_script.py` |
| Demo-liveness (audit verify, mode hot-swap, backend recovery) | `tests/jevcity/test_liveness.py` |
| Edge + negative paths (404/409/422), what-if residue snapshot | `tests/jevcity/test_edge_coverage.py` |
| Replay recordings + path-traversal guard | `tests/jevcity/test_replay.py` |
| Feature engineering | `tests/jevcity/test_features.py` |
| ML dataset/model/wrapper contracts | `tests/jevcity/test_ml_dataset.py`, `tests/jevcity/test_ml_models.py`, `tests/jevcity/test_wrapper.py` |
| Event-pipeline load/latency check (bench, not pytest) | `benchmarks/jevcity_pipeline_bench.py` |

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
