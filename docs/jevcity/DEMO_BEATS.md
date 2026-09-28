# Demo Acceptance Matrix (plan §6, 17 beats → 11 graded + 6 optional)

Graded beats must pass for demo sign-off; optional beats are bonus/rehearsal-time.

## Graded (11)

| # | Beat | Required behavior | Pass criteria |
|---|------|-------------------|---------------|
| 1 | Start normal city state | seeded replay runs | `/api/state` polls clean, no errors |
| 2 | Trigger major accident | valid incident created | incident shows source, type, location, simulated time |
| 3 | ML estimates | severity + traffic return | scores, confidence, `model_version` visible per model contract |
| 4 | Anomaly flags bad input | dq + situational split | anomaly output shows both fields + reasons |
| 5 | Engine marks CRITICAL | **≥2 independent model signals** cross thresholds | priority=CRITICAL after policy validation; may co-exist with AUTO or HOLD |
| 6 | Model failure injection | failed model | decision → MODEL_DEGRADED / human; never auto |
| 7 | Human override | operator + reason | override lands in audit; original decision still visible |
| 8 | What-If safety | sandbox run | `dry_run=true`, zero live writes (audit count unchanged) |
| 9 | Contention | drain required resources | CONTENTION_ESCALATION, no fake allocation |
| 10 | Laya advisory shown | suggestion vs final side-by-side | `laya.suggested_priority` ≠ final → warning shown; structured reasons listed |
| 11 | Laya degraded (timeout/invalid) | forced failure | policy-only fallback decision; `laya.status` visible; system keeps operating |

## Optional (6)

| # | Beat | Notes |
|---|------|-------|
| 12 | Bad-data injection modes | 3 modes demoed if time |
| 13 | Second-emergency scenario | contention angle |
| 14 | State-influence resistance (adversarial notes) | invariant 16 showcase |
| 15 | Deterministic Laya replay | cache-mode same-hash proof |
| 16 | Resource option budget | option-budget guard (Invariant 13) |
| 17 | Calibration gate walkthrough | ECE fixture results (needs Phase-0 item 21 fixtures) |

## Notes

- Laya explanation caveat (plan §6): Laya produces **no NL explanation** — dashboard shows
  suggestion (priority, answer_confidence, distribution) + final decision + structured reasons.
- Multilingual beat (plan) not included: repo pins English `typed-decisions` checkpoint.
- Beats 3/4 use stub models (`sev-rule-0.1.0`, `traffic-heuristic-0.1.0`,
  `anom-threshold-0.1.0`) — graded on contract shape + status handling, not accuracy.
