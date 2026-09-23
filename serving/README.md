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
(stage timings recorded per decision). Calibration is applied at serve time:
`refund_p_calibrated = sigmoid(logit(p) / 0.45)` — the recipe fit out-of-fold in
[`evals/calibrate.py`](../evals/README.md).

## Files

| File | Purpose |
|---|---|
| `pipeline.py` | Stages, `DecisionService`, `AuditLog`, `replay()` — importable as a library |
| `app.py` | FastAPI wrapper: `POST /decide`, `GET /audit/{id}/replay`, `GET /healthz`, `GET /metrics` (Prometheus text) |
| `loadtest.py` | Batch driver over the 50 golden tickets; prints P50/P95 and verifies audit replay |
| `audit.db` | SQLite WAL audit log (runtime artifact, gitignored) |

## Usage

```bash
# Load test over the golden set (4 rounds × 50 tickets)
.venv-bench/bin/python serving/loadtest.py --rounds 4

# HTTP service
.venv-bench/bin/uvicorn serving.app:app --port 8100
curl -s localhost:8100/healthz
curl -s -X POST localhost:8100/decide \
  -H 'content-type: application/json' \
  -d '{"text": "I was charged twice this month and need a refund", "language": "en"}'
curl -s localhost:8100/audit/<decision_id>/replay
curl -s localhost:8100/metrics
```

## Measured (M1 Pro, 2026-09-23, payload v2)

| Metric | Result | Target |
|---|---:|---|
| End-to-end P50 | **80.1 ms** | ≤ 150 ms ✅ |
| End-to-end P95 | **135.3 ms** | ≤ 400 ms ✅ |
| Decision stage share | 79.96 ms | every other stage < 0.1 ms |
| Audit replay | 20/20 identical | bit-for-bit ✅ |

## Operational notes

- **First request costs ~1.1 s** (lazy model load). Put a warmup ping in your
  healthcheck before taking traffic.
- The policy router thresholds (`CONF_AUTO=0.60`, `CONF_REVIEW=0.35`) are
  v1 placeholders from blueprint §4 — recalibrate on golden results before
  trusting AUTO routing.
- `privacy_scan` is the v0 regex layer; the Presidio-backed scan is Phase 1.
  Treat its verdicts as a guard, not a compliance certification.
- Prometheus histograms only render after the first observed request.
