# Laya Failure Modes

Plan §Phase 6 Laya failure tests + latency-budget behavior. Source of truth:
`jevcity/decision_engine/laya_adapter/adapter.py` (resilience), `normalize.py`
(validation), `guardrail/policy.py` (fallback). Tests:
`test_laya_adapter.py`, `test_resilience.py`, `test_laya_schema_battery.py`,
`test_audit_phase4.py`, `test_e2e_pipeline.py::test_laya_timeout_degradation_composite`.

## Fail-closed ladder (item 19)

`MOCK` → `CACHE` → deterministic rule engine (policy-only decision) → `HOLD_FOR_HUMAN`.
No failure path guesses, auto-approves from Laya, or crashes the pipeline (Inv 12).

## Runtime failure modes (in-process laya-mlx, LIVE mode)

| Mode | Detection | Behavior | Test |
|---|---|---|---|
| Timeout (> `LIVE_TIMEOUT_S = 10.0`) | thread-timeout around `agent.predict` | `LayaStatus.TIMEOUT`, `error_code=forced_timeout`/timeout, retry ≤ 2 attempts, breaker; policy decides (`R-LAYA-FALLBACK-POLICY-ONLY-01`) | `test_live_mode_fails_closed_on_timeout`, `test_forced_timeout_status`, F4 composite |
| Unreachable / predict raises | exception from `agent.predict` | `LayaStatus` failed, fail-closed, retry then breaker | `test_live_mode_fails_closed_on_predict_error`, `test_wrapper_exception_status` |
| Circuit breaker open (3 failures, probe every 5th call) | `_live_failures ≥ 3` | fail-fast without calling model until probe | `test_resilience.py` (fail-fast/half-open) |
| Model not loaded / lazy-load error | loader raises | failed response, health probe reports `breaker_open`/load state | `test_health_probe_reports_runtime_readiness` |
| Empty / unextractable response | `to_raw()` → `None` | `LayaStatus` failed path, no guessing | `test_live_mode_fails_closed_on_unextractable_raw`, `test_to_raw_*` battery |
| Missing answer / invalid choice / invalid probability / option overflow / bad sum | `normalize()` raises→failed | `LayaStatus.INVALID_RESPONSE`, `error_code=invalid_output:…` | `test_laya_schema_battery.py` (12 cases) |
| Validation failure surfaces | decision record + audit | `laya.status`, `laya_fallback_used=true`, `laya_final_decision_source=fallback_rule` | `test_laya_timeout_and_invalid_response_are_auditable` |

Breaker / retry constants: `LIVE_MAX_ATTEMPTS = 2`, `LIVE_BREAKER_THRESHOLD = 3`,
`LIVE_BREAKER_PROBE_EVERY = 5`, `LIVE_TIMEOUT_S = 10.0`.

## Latency-budget behavior (plan §6 "Latency test budget")

When Laya exceeds the decision latency budget (simulated by forced timeout):

1. the **fallback decision is still shown** — policy-only record, never a crash
   (`dec.state ∈ {MODEL_DEGRADED, HOLD_FOR_HUMAN}`, never `AUTO_APPROVED` from Laya);
2. the **dashboard marks `laya_degraded`** — `GET /api/state.last_laya_status =
   "timeout"`, inspector badge + `last_laya_status` polling;
3. the **audit records the timeout** — `laya.laya_status = timeout`,
   `laya_fallback_used = true`, questions version + state hash intact.

One test asserts all three surfaces:
`tests/jevcity/test_e2e_pipeline.py::test_laya_timeout_degradation_composite`.
Measured latency budgets (pass): M1 Pro 61.6–93.6 ms/3-question decision vs 250 ms
(demo) / 750 ms (CPU); pipeline benchmark: `benchmarks/jevcity_pipeline_bench.py`.

## Sidecar-only modes — documented N/A (ERRATA C1)

The plan's HTTP-sidecar failure list does not map 1:1 onto the in-process runtime;
these are **not exercised** because `laya-serve` is not used:

| Plan-sidecar failure | In-process reality |
|---|---|
| Malformed JSON from HTTP response | No JSON transport — `to_raw()`/`normalize()` validate typed dicts instead (battery above) |
| Checkpoint download failure | Load errors surface via lazy-load failure → same fail-closed path as "model not loaded" |
| Out of memory | Process-level; not catchable in-process — mitigated by fp16 + ~804 MiB weights (checkpoint card) |
| Invalid device | `DEVICE="mps"` compiled constant; Apple-silicon-only package (pyproject) makes mismatch a startup error |
| Unsupported question type | Question schema frozen (`q-0.1.0`, Inv 14) — `LayaRequest`/`QUESTIONS` reject anything else before the call |

## Degraded UX surfaces

- API: `last_laya_status`, `laya_mode`; decision `laya.status`, `laya.final_decision_source`.
- Dashboard: inspector status badge, fallback banner, `MODEL_DEGRADED`/`HOLD` states,
  `laya_proposed` vs `policy_finalized` divergence indicator.
- Audit: full `AuditLayaMetadata` per decision (Phase 4 contract).
