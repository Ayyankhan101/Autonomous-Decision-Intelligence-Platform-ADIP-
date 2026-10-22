# JevCity User Guide

**What it is, who it is for, how to drive it, and where it stands today.**

JevCity is the incident-triage vertical of the Autonomous Decision Intelligence
Platform (ADIP). It simulates city incidents (fire, accident, flood, traffic spike),
runs each through an ML + Laya decision pipeline, and puts a **deterministic policy
guardrail** in final authority: *Laya proposes; the guardrail decides.* Every
decision is written to an append-only, hash-chained audit log.

Run it locally, drive it from a browser dashboard, and verify every claim against
checked-in artifacts.

New here? The [Quick start](#quick-start) gets you from clone to a live incident
decision in under 5 minutes. Looking for API contracts? See [`API.md`](API.md).
Preparing a demo? See [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md).

---

## Who it is for

| Reader | What this guide gives you | Companion doc |
|---|---|---|
| **Operator** (demo driver, student presenting) | Quick start, incident lifecycle, overrides, policy switch, What-If, vision evidence, troubleshooting | [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) — exact clicks, seeds, pass criteria |
| **Evaluator** (grader, reviewer) | Status snapshot with every number traceable to a checked-in artifact | [`QA.md`](QA.md) (findings), [`ERRATA.md`](ERRATA.md) (plan-vs-repo resolutions) |
| **Contributor** | Where tests, lint, contracts, and architecture live | [`ARCHITECTURE.md`](ARCHITECTURE.md), [Contributor appendix](#contributor-appendix) |

---

## Live mode (workstream B)

Run against real free public feeds (no API key):

```bash
JEVCITY_FEED_MODE=live uv run uvicorn jevcity.api.app:app --port 8200
```

What changes in live mode:

- **Header**: wall-clock PKT (UTC+5) replaces simulated clock; cyan LIVE badge; seeds hidden.
- **ContextStrip** (under KPIs): weather chip (temp/precip/flood risk), GDACS chip (alerts), last ReliefWeb advisory.
- **Incident stream**: Open-Meteo (weather → flood), USGS (seismic → traffic_spike), GDACS (orange/red FL/EQ within 300 km); ReliefWeb advisories for context only.
- **Station coords**: 17 Peshawar units at real Rescue 1122 / fire-station / police-post coords (static until real GPS telemetry available).
- **Inject form**: labelled "Manual Report" — same validation + trust path.
- **Circuit breaker**: 3 consecutive feed failures → held open, probe after cooldown; dashboard shows feed status honestly, never fakes green.

Honest labeling: traffic synthetic (weather-modulated); Rescue 1122 CPS integration pending — no public API.

Mock mode (`JEVCITY_FEED_MODE=mock`, default) keeps the full deterministic seeded pipeline for demos, evals, and CI.

### Audit persistence

The audit store is durable by default: `build_engine` writes a SQLite hash chain to `jevcity/audit/audit.db` (repo-relative; env override: `JEVCITY_AUDIT_PATH=/path/audit.db`; `:memory:` for throwaway runs; gitignored via `jevcity/audit/*.db*`). The SHA-256 chain survives restarts — reopen `AuditLog` on the same path and `/api/audit/verify` still reports ok, with entry numbering continuing where it left off. The DB file is gitignored (`.gitignore:15`); tests pin `:memory:` via an autouse conftest fixture so runs stay isolated.

---

## What JevCity is

A seeded, deterministic simulation city feeds incidents through this pipeline
(details in [`ARCHITECTURE.md`](ARCHITECTURE.md)):

```
simulation (seeded clock, no host wall-clock)
  → ingestion.validate      hard-reject malformed input, soft-flag the rest
  → ingestion.correlate     group reports into incidents, detect contradictions
  → features.engineer       simulated-time features
  → ML triad                severity · traffic · anomaly (local, versioned)
  → Laya adapter            mock | cache | live  — the advisory layer
  → guardrail               16 invariants; final authority (Invariant 10)
  → allocation              greedy dispatch from the resource pool
  → decision record         → append-only hash-chained audit
```

Key ideas:

- **Propose/decide split.** Laya (an on-device typed-decision model via
  `laya-mlx`, Apache-2.0, private by architecture) proposes; deterministic policy
  rules decide. Laya can be wrong, time out, or be swapped out entirely —
  decisions still land, or fail closed, with the reason recorded.
- **Trust but verify.** Per-stream trust scoring downweights suspicious report
  sources; a Sybil-flood injector exists so you can watch it work.
- **Override friction.** A human can override any decision, but the server
  grades the override's projected impact into `LOW`, `HIGH`, or `BREAK_GLASS`
  tiers and demands acknowledgment/justification proportional to the risk.
- **What-If sandbox.** Ask "what if an ambulance disappears?" without touching
  live state — sandboxes never write audit and never mutate the simulation.
- **Vision evidence.** Attach a photo; a local VLM extracts structured facts
  (`VisionFacts`) that flag mismatches as *evidence, never authority* — the
  guardrail and ML triad stay in charge.
- **Honest failure.** Model gates are deliberately left at their measured
  (uncalibrated-confidence) values — see [ERRATA C4](ERRATA.md). The system
  reports what it measured, not what the plan hoped.

---

## Quick start

Prereqs: Python 3.13, [`uv`](https://docs.astral.sh/uv/), and for the dashboard
build path Node 20+ with `pnpm` (optional — prebuilt assets are served by the API).

```bash
# 1. Start the API (serves the dashboard too, when dashboard/dist exists)
uv run uvicorn jevcity.api.app:app --port 8200
```

Open **http://localhost:8200**.

```bash
# 2. In the dashboard: press "Start Sim" (seeds 42 / 7 are pre-filled)
# 3. Under SIMULATE INCIDENT pick Fire → North Sector → severe → Inject
```

Within a second you should see: a decision card (`inc-00001`, severity, Laya
advisory vs final policy decision), a fire truck marked dispatched in the fleet
pool, an audit entry in the Audit Trail tab, and the sim clock stepping. That is
the whole pipeline, end to end.

Prefer live development mode with hot reload:

```bash
uv run uvicorn jevcity.api.app:app --port 8200   # terminal 1
cd dashboard && pnpm install && pnpm dev         # terminal 2 → :5173, proxies /api
```

---

## How to run an incident lifecycle

1. **Start a session** — `Start Sim` (or `POST /api/simulation/start` with
   `{session_seed, scenario_seed}`). Note: `start()` **resets** state; to pause
   and come back, use Pause → Resume (resume keeps the session).
2. **Inject an incident** — SIMULATE INCIDENT panel. Severity is a hint; the ML
   triad + guardrail compute the real priority. Multi-report incidents
   (`multi_report`) exercise correlation; contradictory reports route to human
   review instead of auto-deciding.
3. **Watch the decision** — the incident card shows priority, assigned units,
   Laya's advisory, matched policy rules, and (via the decision detail) full
   **lineage**: which evidence terms and clauses drove the outcome.
4. **Override if needed** — open the incident → Override. The server classifies
   your override:
   - `LOW` — just operator + reason required.
   - `HIGH` — you must acknowledge impact (`impact_ack`) and cite a context code.
   - `BREAK_GLASS` (e.g. raising a life-safety priority) — explicit
     `break_glass` flag required.
   Use the **impact preview** (`POST /api/overrides/impact`) first — it is a dry
   run that never mutates anything and tells you which tier you will hit.
5. **Verify the trail** — Audit Trail tab, or `GET /api/audit?limit=50`
   (newest-first). Entries are append-only and hash-chained.

Fault paths worth demoing: `SIMULATE → BAD DATA` (missing fields / out of range /
conflicting reports / adversarial notes) produces `REJECTED_INPUT` or
`HOLD_FOR_HUMAN` decisions with the reason on the record — not a crash.

---

## How to use the policy sandbox

The header shows the active policy position: `RESPONSE_TIME` (default), `EQUITY`,
or `ECO`.

- Switch in the dashboard (Policy section) or `POST /api/policy/position`.
- New decisions follow the new weights immediately.
- Check **reoptimise** to re-decide all *open* incidents under the new position
  (units are released and reassigned; resolved incidents stay untouched).
- The switch writes a `POLICY_POSITION_SWITCHED` audit entry and persists across
  simulation start/reset — only another explicit switch changes it.

Watch `R-EQUITY-UNSERVED-01` or `R-ECO-ELECTRIC-FIRST-01` appear in matched rules
to see which objective won.

---

## How to run a What-If

What-If Sandbox tab, or the API:

```bash
POST /api/what-if/run   {"scenario": "remove_one_ambulance" | "close_road" | "second_emergency"}
GET  /api/what-if/{sandbox_id}/result
```

Results always carry `dry_run=true, audit_written=false, live_state_mutated=false`.
A sandbox runs on an isolated copy: RNG states, resource pool, and counters are
snapshotted and restored, so residue in the live system is zero.

---

## How to attach vision evidence

1. Pick an incident → Vision panel → upload an image (PNG/JPEG/WebP, ≤ 5 MB,
   validated by magic bytes).
2. The extractor returns structured `VisionFacts` (smoke, vehicles, injuries…)
   and a `severity_mismatch_vision` soft flag when the photo disagrees with the
   reported severity.
3. Facts attach to the incident as evidence — `VISION_ATTACHED` audit entry,
   sim-clock timestamped. The guardrail does not change; evidence informs the
   human, it does not decide.

Runtime modes (header, VISION RUNTIME block, or `POST /api/vision/mode`):

| Mode | Behavior |
|---|---|
| `mock` (default) | Deterministic synthetic facts; zero dependencies |
| `cache` | Recorded real extractions, replayed |
| `live` | Local MLX VLM — needs `uv sync --extra vision`; fails closed (status `unavailable`) when the runtime is absent |

---

## How to verify the audit trail

- **UI:** Audit Trail tab — newest-first list with actor, action, target, hash.
- **API:** `GET /api/audit/verify` recomputes the full SHA-256 chain now and
  returns `{ok, entry_count, broken_at}`. `ok: true` means every entry's
  `entry_hash` matches its contents and its predecessor.
- **Invariant:** no endpoint can update or delete audit rows; the log is
  INSERT-only. If a write ever fails, the API stays up, raises
  `audit_write_failed` in `/api/state`, and the dashboard shows the
  AUDIT WRITE FAILED banner.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Banner `BACKEND UNREACHABLE: Failed to connect to JevCity API at ht…` | API process died or port changed | Restart `uvicorn … --port 8200`; dashboard auto-reconnects on the next poll and the banner clears |
| Stale numbers after backend restart | Sim session reset server-side | Press **Refresh Data** (or reload); polling also self-heals within 1.5 s |
| AUDIT WRITE FAILED banner | Audit log write rejected (disk/permissions) | Fix the host issue, then trigger any write or `/api/simulation/reset`; banner clears on next successful append |
| `live` vision mode shows `unavailable` | MLX vision extras not installed | `uv sync --extra vision`; mode hot-swaps, no restart needed |
| `live` Laya mode slow or fallback | Checkpoint unavailable / timeout / invalid output | Expected fail-closed path: decision proceeds via policy with `laya_fallback_used` recorded — see [`LAYA_FAILURE_MODES.md`](LAYA_FAILURE_MODES.md) |
| Dashboard tab in background | Polling auto-pauses when tab is hidden | Return to the tab — it refetches immediately and resumes polling |

---

## Current status

Every row below is reproducible from a checked-in artifact — commands in the
[Contributor appendix](#contributor-appendix).

| Dimension | Status (October 2026) |
|---|---|
| **Scope** | Phases 0–7 complete: pipeline, eval runner, serving, JevCity vertical slice, Command Center dashboard, demo runbook |
| **Tests** | 335 model-free + 6 model-tier (live-checkpoint and vision smokes) = **341**; model-free suite runs in ~12 s |
| **API** | **30 routes** (16 plan-frozen + 14 additive) on port 8200 — ledger: `tests/jevcity/test_audit_phase4.py::FROZEN_ROUTES` |
| **QA** | 4 black-box/browser loops + deeper pass (ECO switch, live-vision fail-closed, upload idempotency) — all clean; findings F-B1…F-B13 closed ([`QA.md`](QA.md)) |
| **Delivery** | PRs **#18–28** merged: backlog cleared, user-journey + deeper QA passes, suite/polling optimizations (parallel test waves, combined `GET /api/dashboard` poll bundle, latest-decision index, hidden-tab pause) |
| **Decision latency** | 61.6–93.6 ms per 3-question Laya decision on M1 Pro (`benchmarks/results/*.json`) — `laya-mlx==0.2.0`, in-process |
| **Dashboard polling** | 1 request per 1.5 s (`GET /api/dashboard` bundle); pauses while the tab is hidden |
| **Determinism** | Seeds 42/7, sim-clock epoch `2026-09-27T10:00Z`, no host wall-clock anywhere in scoring paths |
| **Honest gates** | Severity accuracy/ECE gate intentionally **left failing** at measured values ([ERRATA C4](ERRATA.md)); confidence treated as uncalibrated by contract |
| **Runtime footprint** | No external services: ML triad, Laya (mlx), audit, API all local; dashboard bundle ≈ 96 KB gzipped |

Known limitations (all documented, none silent): Laya confidence is uncalibrated
until fixture-measured; `live` modes need optional extras; the plan document's
`laya-serve` sidecar claims are unverified and unused ([`ERRATA.md`](ERRATA.md)).

---

## Contributor appendix

```bash
uv run pytest -q                 # 335 model-free tests (model-tier deselected)
uv run pytest -q -m model        # 6 model-tier tests (downloads/checkpoints)
uv run python -m jevcity.schemas.export   # regenerate schemas/*.json after contract changes
cd dashboard && pnpm lint && pnpm build   # oxlint + production build
uv run python -m ruff check jevcity/ tests/
```

- Contracts: `jevcity/schemas/` (Pydantic, additive-only, `extra="forbid"`) +
  exported JSON Schema in `schemas/*.json` (byte-compared in CI freshness test).
- Route surface is frozen by `FROZEN_ROUTES`; additive endpoints get an explicit
  ledger entry + test.
- Architecture decisions live in [`ARCHITECTURE.md`](ARCHITECTURE.md); plan-vs-
  repo conflicts are resolved in [`ERRATA.md`](ERRATA.md); the guardrail's 16
  invariants in [`GUARDRAIL.md`](GUARDRAIL.md).
- PRs need green CI (ruff + model-free suite) before merge.

## Related documents

| Doc | For |
|---|---|
| [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md) / [`DEMO_BEATS.md`](DEMO_BEATS.md) | Rehearsed demo script, exact clicks, pass criteria |
| [`API.md`](API.md) | Full endpoint reference with request/response shapes |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Pipeline internals, module map |
| [`QA.md`](QA.md) | Test-loop findings, known limitations history |
| [`ERRATA.md`](ERRATA.md) | Plan-document claims vs measured reality |
| [`GUARDRAIL.md`](GUARDRAIL.md) | The 16 invariants and override friction rules |
| [`../../README.md`](../../README.md) | Platform-level (ADIP) overview, eval harness, triage stack |
