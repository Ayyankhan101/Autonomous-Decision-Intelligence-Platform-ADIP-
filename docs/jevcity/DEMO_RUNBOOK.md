# JevCity Demo Runbook (Phase 7)

Technical demo script: exact seeds, exact clicks, expected state, pass criteria.
Companion matrix: [`DEMO_BEATS.md`](DEMO_BEATS.md) (19 beats, 11 graded).
Plan refs: §6 Demo Acceptance Matrix, §Phase 7 Demo Rehearsal & Polish,
DoD items 16 (rehearsed ≥2×), 18 (fallback recording), 29 (run with Laya disabled).

## 0. Fixed demo parameters

| Parameter | Value |
|---|---|
| Session seed | `42` |
| Scenario seed | `7` |
| Backend | `python -m uvicorn jevcity.api.app:app --port 8200` |
| Dashboard | `pnpm dev` → `http://localhost:5173` |
| Laya mode (graded beats) | `mock` (deterministic; switch to `live` only for the model-failure / advisory beats if rehearsed) |
| Browser | Chromium, 1440×900, no extensions |

## 1. Pre-flight (2 minutes)

1. Backend health: `curl -s localhost:8200/api/state` → `running`, `audit_write_failed: false`.
2. Dashboard loads, header freshness ticker (`upd Ns ago`) advances, no console errors.
3. KPI strip ticks after start (Open Incidents, Decisions Emitted, Avg Laya Latency sparkline, Fleet Deployed %).
4. `/api/audit/verify` returns `ok: true` (or green **Verify** button on Audit Chain card after a few decisions).
5. Laya badge reads `MOCK` (graded) — never demo on an untested mode.
6. Fresh state: **Stop/Reset** to seed 42/7 if the machine has residual incidents.

## 2. Beat script — graded 11

| # | Action (exact click) | Expected state | Pass |
|---|---|---|---|
| 1 | Start session (SimulationControls ▶, seeds 42/7) | `/api/state` polls clean; ticker advances; no errors | polls 200, banner absent |
| 2 | **Inject Incident** — accident, zone North | incident card `inc-*`, source list, simulated time | incident appears MapLayer + Event Feed |
| 3 | Open incident → model cards | severity + traffic scores with confidence, `model_version` | each model contract fields visible |
| 4 | **Inject bad data** (mode: mixed severity) | anomaly output: `dq` + `situational` split + reasons | both fields rendered |
| 5 | Wait ≤2 s for decision | priority **CRITICAL** (≥2 independent signals) | record shows ≥2 matched rules; may co-exist with AUTO/HOLD |
| 6 | Force model failure (bad-data / upstream kill) | decision → `MODEL_DEGRADED` or `HOLD_FOR_HUMAN` | never auto-approved; `laya.status` visible |
| 7 | Override on a decision | operator id + reason required (empty → 422) | `OVERRIDE_ACTIVE` in AuditTrail, original decision still visible |
| 8 | **What-If** sandbox run | `dry_run=true` result card | audit entry count unchanged (Verify before/after) |
| 9 | Drain resources (dispatch fire trucks) | contention on next decision | `CONTENTION_ESCALATION`, no fake allocation |
| 10 | Advisory decision (mock/live) | side-by-side `laya.suggested_priority` vs final | warning shown when they differ; structured reasons listed |
| 11 | Force Laya timeout/invalid | policy-only fallback decision | system keeps operating; `laya.status` degraded visible |

## 3. Optional beats (rehearsal-time)

- **12** bad-data modes (3), **13** second emergency mid-run (live re-arbitration),
  **14** adversarial notes in `notes` field → invariant 16 holds,
  **15** cache-mode replay → same `state_hash`/`questions_hash`,
  **16** option-budget guard, **17** calibration fixtures,
  **18** policy sandbox: switch RESPONSE_TIME → ECO, weights bar animates, badge flips,
  **19** Sybil Flood button → Stream Trust mean ~0.63, fakes fuchsia,
  `R-TRUST-DOWNWEIGHT-01` visible; clean contrast = mean 1.00.

## 4. Rehearsal protocol (DoD 16)

1. Two full end-to-end runs from cold start, final demo seed (42/7), final mode.
2. Zero unplanned manual intervention — scripted actions only; triage table (§6) for failures.
3. Log each run (start/end time, beats hit, deviations) in this file's §7 table.
4. Any failed beat → fix or explicitly move to Advanced Extensions (scope freeze, §Phase 7).

## 5. Fallback recording (DoD 18)

1. Record one complete passing run (screen + audio) after rehearsal 2 passes.
2. Capture: pre-flight, all 11 graded beats, Verify seal green, final AuditChain verify.
3. Store as `demo-fallback.mp4` (not committed; submission media location per course brief).
4. Live failure during presentation → switch to recording; no on-stage debugging.

## 6. Live-failure triage

| Symptom | Cause | Fix (<30 s) |
|---|---|---|
| `BACKEND UNREACHABLE` banner | uvicorn died | restart backend cmd, refresh page |
| `AUDIT WRITE FAILED` banner | audit path/disk issue | check server logs/disk; Reset clears flag after fix |
| Latency stuck, Laya badge red | `live` mode timeout | header → `mock` (deterministic, honest label) |
| Stale incident state | poll paused | check ticker; force refresh via Start |
| Chain verify red | tamper (expected in tamper demo) | note broken_at entry, Reset for clean chain |
| Contention with no output | resources drained | dispatch a unit or Reset |

## 7. Rehearsal log

| Run | Date | Mode | Result | Deviations |
|---|---|---|---|---|
| 1 | _pending_ | mock | | |
| 2 | _pending_ | mock | | |
