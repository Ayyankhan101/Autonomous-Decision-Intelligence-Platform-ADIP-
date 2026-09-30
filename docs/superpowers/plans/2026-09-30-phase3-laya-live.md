# Phase 3 — Laya LIVE integration + deterministic guardrails

Status: executing. Start 2026-09-30.
Source: plan-of-record §Phase 3 (Laya rename) + `PHASE0_SIGNOFF.md` items 12, 17-note, 18.
Execution: in-session (SDD `delegate_task` harness broken — ledger deviation, Phase-2 precedent).
Landing: **branch → PR → `lint + model-free tests` green → rebase-merge** (main-protection ruleset id 24235972; direct pushes blocked by design).
Ledger: `.superpowers/sdd/2026-09-30-phase3-laya/progress.md`

## Global constraints (carry-over)

- Schemas additive-only, `extra="forbid"`; **16 API endpoints frozen** (health check = internal, no endpoint).
- No host wall-clock in features/labels/fixtures (measured latency logging OK).
- No inline code comments (docstrings OK). Ruff `E9,F`, line-length 100.
- Frozen: model versions (sev-gb-1.0.0 / traffic-gbr-1.0.0 / anom-ml-1.0.0), C4 gates 0.70/0.15
  (report numbers only), checkpoint `aac6fef/laya-typed-decisions-mlx`, DTYPE float16.
- Fail-closed precedence unchanged: REJECTED_INPUT > MODEL_DEGRADED(upstream) > HOLD_FOR_HUMAN >
  MODEL_DEGRADED(Laya-only) > CONTENTION_ESCALATION > AUTO_APPROVED.
- Guardrails policy invariant 1–16 tests must stay green.
- New tests: model-free unless marked `model`; live-only tests marked **`model` + `laya_live`**.

## C1 findings (completed 2026-09-30, pre-plan introspection)

Live probe: `laya_mlx.load(CHECKPOINT, dtype="float16", batch_size) → agent.predict(render_state(state), QUESTIONS)`.

1. Result shape: `{"answers": {...}, "model": ..., "usage": ...}`.
2. `answers.priority` / `answers.recommended_resource_type` = `{action, choice, confidence, probabilities, type}`;
   `answers.needs_human_review` = `{action, confidence, noul, type}`.
3. **No upstream `answer_confidence` on any answer** → signoff item 18 resolves: upstream field does
   not exist; ERRATA C2 derivation in `to_raw`/`normalize` IS the contract. Upstream separate
   `confidence` field exists but is intentionally unused (eval measures derived confidences — keep,
   document).
4. `QUESTIONS` accepted by live `agent.predict` → item 17 note closes (schema shape empirically valid).
5. `laya_mlx` RuntimeWarning: checkpoint temperatures outside [0.5, 5] clamped by the library →
   confidence uncalibrated (confirms ERRATA C3).
6. Warm-up: first `predict` after load ~1–2 s (thread timeout must cover load+predict or pre-warm).

## Tasks

- [ ] **C2 — `adapter.health()`**: internal probe (mode, checkpoint, dtype, device, agent_loaded,
      errors). No new endpoint. Test in `tests/jevcity/test_laya_adapter.py` (model-free).
- [ ] **C5 — LIVE mode core**: extract `adapter._live_call(state, questions) -> dict` (imports
      `laya_mlx` lazily, module-level agent cache, warm on first use). LIVE branch replaces
      `live_integration_phase3` stub (adapter.py:78): call → shared raw extraction → `normalize(...)`
      → cached per cache-key semantics? (LIVE responses NOT cached by default — cache mode stays
      explicit; document). Timeout via single-worker thread `future.result(timeout)`; measured
      latency; `result["model"]` recorded. Move `to_raw` from `evals/run_jevcity_eval.py` →
      `jevcity/decision_engine/laya_adapter/normalize.py` (shared, eval imports it — no behavior
      change). Fail-closed on every exception path (statuses handled by existing inv9/inv12).
- [ ] **C3 — retry policy**: LIVE call path retries **TimeoutError only**, max 2 attempts total,
      immediate (no sleep — in-process MLX), anything else fails immediately. Unit tests via
      monkeypatched `_live_call`.
- [ ] **C4 — circuit breaker**: consecutive failure count (timeouts/exceptions) ≥3 → OPEN → instant
      `failed(UNAVAILABLE, error_code="circuit_open")` without calling; every 5th blocked call =
      half-open probe; probe success → CLOSED (reset), failure → OPEN. Call-count based, no clock.
      Tests in `tests/jevcity/test_resilience.py` (model-free, monkeypatch).
- [ ] **C6 — upstream contract verification** (`tests/jevcity/test_laya_live.py`,
      `pytestmark = [model, laya_live]`): live predict on fixture state → assert answers keys
      (`choice/probabilities/noul/action/type/confidence`), **assert `answer_confidence` absent
      upstream**, derived value flows through `normalize` (C2), two runs byte-identical answers
      (determinism), latency measured >0. Closes signoff 18 + 17-note with measured truth.
- [ ] **C7 — injection resistance (Inv16)**: property tests — adversarial notes/field text
      (`IGNORE ALL PREVIOUS`, newlines, control chars, oversized) never appear raw in
      `render_state` output; rendered length bounded. Extend `tests/jevcity/test_laya_adapter.py`.
- [ ] **C8 — decision-source live path**: tests driving engine with LIVE adapter (monkeypatched
      happy path + failures) → `DecisionSource` = `LAYA_PROPOSED` / `POLICY_FINALIZED` /
      `FALLBACK_RULE` / `HUMAN_REQUIRED` all reachable on live path; every decision carries
      policy_version (existing assertion extended to live path).
- [ ] **C9 — CI wiring**: register `laya_live` marker (pyproject), add `LayA live smoke` step
      (`pytest -q -m laya_live`, timeout 5) after model tier step (split `-m "model and not
      laya_live"` already in place). Closes signoff 12 with CI evidence.
- [ ] **C10 — docs/sign-off/push**: close items 12, 18 (+17 note) → **Gate 1 verdict 🟡 → ✅**;
      ERRATA C1 addendum (in-process laya_mlx verified live; laya-serve/HTTP/CLI remain unverified);
      ARCHITECTURE §LIVE mode (retry/breaker/health); full suite + ruff; branch → PR → CI watch
      (C4 warn+summary step fires) → rebase-merge; final in-session review; ledger + workspace cleanup.

## Risks / open decisions (record in ledger at execution)

- `laya_live` smoke on macos-14 runner: untested environment (MLX wheel on GH runners) — first main
  run may need adjustment; local machine verified green (C1/C6).
- Thread-timeout cannot kill a hung MLX call (daemon worker leaked) — acceptable: fail-closed
  response returned, breaker opens, process continues.
- LIVE + cache interplay: CACHE mode keeps mock-derived answers (demo replay); LIVE never writes
  the demo cache unless mode == CACHE (verify no key collision across modes — cache key includes
  checkpoint/dtype but not mode → document or include mode).
