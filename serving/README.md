# Phase 0 Serving Pipeline

The **first real end-to-end measurement** of the blueprint's ≤ 150 ms pipeline KPI
(§12 previously recorded "—" here). Everything runs locally on Apple Silicon via
laya-mlx; no state leaves the machine.

## Architecture (blueprint §3, realized)

```
ticket text
  → privacy_scan      redaction + PII guard (v0: regex layer; Presidio is Phase 1)
  → fairness_screen   protected-attribute flags (serving path records, never decides)
  → typed_decision    laya agent.predict() — department / urgency / refund
  → policy_router     AUTO_DECIDE / REVIEW / ESCALATE from confidence thresholds
  → explanation       template-rendered why-string from the typed answers
  → AuditLog          SQLite (WAL) row; replay() recomputes and compares bit-for-bit
```

Pure-function stages in `pipeline.py`, orchestrated by `DecisionService`
(stage timings recorded per decision). Calibration is applied at serve time for
both calibrated heads:
`refund_p_calibrated = sigmoid(logit(p) / 0.45)` (out-of-fold fit,
[`evals/calibrate.py`](../evals/README.md)) and the department confidence
`department_conf = p_k^(1/0.6)` renormalised (`adip.config.DEPT_TEMPERATURE`,
Brier-fit + OOF-validated in
[`evals/calibrate_dept.py`](../evals/README.md) /
`evals/results/calibration-dept-20260926.json`). The decision JSON carries the
calibrated `department_dist` (what the router and explanation read) plus
`department_dist_raw` for audit provenance; scalar scaling preserves the
argmax, so routed labels are unaffected.

## Files

| File | Purpose |
|---|---|
| `pipeline.py` | Stages, `DecisionService`, `AuditLog`, `replay()` — importable as a library |
| `app.py` | FastAPI wrapper: `POST /decide`, `GET /audit/{id}/replay`, `GET /healthz`, `GET /metrics` (Prometheus text) |
| `loadtest.py` | Batch driver over the 50 golden tickets; prints P50/P95 and verifies audit replay |
| `audit.db` | SQLite WAL audit log (runtime artifact, gitignored) |

## Usage

```bash
# Load test over the golden set (4 rounds × 50 tickets) — in-process, no HTTP
uv run python serving/loadtest.py --rounds 4        # exit 1 if KPI/replay fails
#   → serving/results/loadtest-<host>-<rounds>r.json

# HTTP service (bearer auth only if ADIP_API_TOKEN is set)
uv run uvicorn serving.app:app --port 8100
curl -s localhost:8100/healthz                      # open (no auth)
curl -s -X POST localhost:8100/decide \
  -H 'content-type: application/json' \
  ${ADIP_API_TOKEN:+-H "authorization: Bearer $ADIP_API_TOKEN"} \
  -d '{"text": "I was charged twice this month and need a refund", "language": "en"}'
curl -s localhost:8100/audit/<decision_id>/replay
curl -s localhost:8100/metrics
```

## Measured (M1 Pro, payload v2, 2026-09-26 load test, 200 distinct-input calls)

| Metric | Result | Target |
|---|---:|---|
| End-to-end P50 | **79.38 ms** | ≤ 150 ms ✅ |
| End-to-end P95 | **137.64 ms** | ≤ 400 ms ✅ |
| `kpi_pass` | `true` | ✅ (loadtest exits 1 otherwise) |
| Decision stage share | 79.31 ms p50 | every other stage ≤ 0.04 ms |
| Audit rows written | 200 / 200 (total 402 in db) | every call lands ✅ |
| Audit replay | 20/20 bit-for-bit | ✅ |
| Route mix | AUTO 84 / REVIEW 112 / ESCALATE 4 | recorded, not a target |
| Shape errors | 0 | ✅ |

Repeating the same short text is cheaper than this (61.6 ms p50 — prefix
cache hits); distinct tickets cost what the numbers above show.

## Operational notes

- **First request costs ~1.1 s** (lazy model load). Put a warmup ping in your
  healthcheck before taking traffic.
- **Auth (opt-in):** set `ADIP_API_TOKEN=<secret>`. `/decide` and
  `/audit/{id}/replay` then require `Authorization: Bearer <secret>`
  (constant-time compare, 401 otherwise). `/healthz` and `/metrics` stay open.
  Unset = no auth (loopback dev).
- **Failures never vanish:** a raised exception in `/decide` returns 500
  `decision failed: <ExcType>` **and still writes an audit row with
  `route=ERROR`**; `adip_errors_total` increments. `replay()` on an ERROR row
  returns 409 (`decision failed (route=ERROR); nothing to replay`) instead of
  a false MISMATCH.
- The policy router thresholds (`CONF_AUTO=0.60`, `CONF_REVIEW=0.35`) are
  v1 placeholders from blueprint §4 — recalibrate on golden results before
  trusting AUTO routing. Since payload v3 they are compared against the
  **calibrated** `department_conf` (raw confidences were under-confident:
  mean 0.69 at 0.78 accuracy), so a threshold now means roughly what it says;
  routing labels themselves are unchanged by the calibration.
- `privacy_scan` is the v0 regex layer; the Presidio-backed scan is Phase 1.
  Treat its verdicts as a guard, not a compliance certification.
- Prometheus histograms only render after the first observed request.
