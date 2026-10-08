# Phase 5 — Command Center Dashboard (plan §Phase 5)

Source: `JevCity_Implementation_Plan_Revised_v2_Laya.docx` Phase 5 (weeks 5–9), `docs/jevcity/DEMO_BEATS.md` (11 graded beats), `docs/jevcity/API.md`, `ARCHITECTURE.md`.
Branch: `stage/phase5-dashboard`.
Execution: in-session.

## Current State (Phases 0–4 Shipped)

- **Phase 0–1**: Seeded simulation clock, deterministic replay, ingestion validation & correlation, multi-report contradiction, bad-data injection.
- **Phase 2**: Real ML models (`sev-gb-1.0.0`, `traffic-gbr-1.0.0`, `anom-ml-1.0.0`), calibrated confidence, latency measurement, timeout/error fallback.
- **Phase 3**: In-process `laya-mlx` live integration, thread-timeout (10s), retry, circuit breaker, fail-closed handling, injection-resistant state builder (Invariant 16).
- **Phase 4**: Immutable SQLite audit log (triggers block UPDATE/DELETE), hash chain with schema-stable `payload_hash`, `AuditLayaMetadata` completeness, read-only frozen route set (16 endpoints), JSONL export CLI (`tools/export_audit.py`). All 191 tests pass, CI green.

## Architectural Constraints (Strict)

1. **Frozen 16 API routes**: Route set `FROZEN_ROUTES` cannot be altered. No new `/api/*` endpoints. Audit remains GET-only.
2. **Schema stability**: Pydantic schemas are additive-only with `extra='forbid'`. Freshness asserted by `tests/test_schemas_export.py`.
3. **Deterministic simulation time**: Dashboard displays simulated clock from `/api/state` (`2026-09-27T10:00:00Z` epoch); no host wall-clock for domain logic.
4. **Authority & Explainability**: Laya proposes, policy decides. The dashboard shows Laya suggestion (priority, answer confidence, distribution) next to the final decision (priority, state) and structured policy reasons. Laya produces no natural-language explanation.
5. **What-If Isolation**: Counterfactual sandbox displays `dry_run=true, audit_written=false, live_state_mutated=false` badge; verifies zero mutation of live audit/decision state.
6. **Code standards**: Ruff `E9,F` clean, line-length 100, no inline comments, clean component architecture.

---

## Tasks Breakdown

### E1: Backend CORS Enablement & API Verification
- Add `CORSMiddleware` to `jevcity/api/app.py` allowing frontend dashboard communication from `localhost:5173` / `localhost:3000`.
- Verify `tests/jevcity/test_audit_phase4.py` (route freeze test) remains 100% green (middleware does not add `/api/` APIRoutes).
- Verify backend tests and schema export tests remain green.

### E2: Frontend Project Scaffold (`dashboard/`)
- Initialize modern Vite + React + TypeScript application in `dashboard/` with Tailwind CSS and Lucide icons.
- Configure Vite proxy to `http://localhost:8200` for `/api/*` requests.
- Generate TypeScript types matching `schemas/*.json` (`StatePayload`, `IncidentRecord`, `DecisionRecord`, `Resource`, `AuditEntry`, `WhatIfResult`, `LayaBlock`, etc.).
- Setup clean Command Center layout (Header, Map view, Incident inspector, Simulation controls, Override modal, Audit trail, What-If drawer).

### E3: Polling Engine & Simulation Control Station
- Polling hook subscribing to `/api/state`, `/api/incidents`, `/api/decisions`, `/api/resources`, `/api/audit` every 1–2s.
- Graceful connection handling: `backend_unreachable` badge if API is down.
- Simulation Controls:
  - Start, Pause, Reset (with configurable `session_seed` and `scenario_seed`, default 42/7).
  - Inject Incident (type, zone, severity, notes, multi_report).
  - Inject Bad Data (modes: `missing_fields`, `out_of_range`, `conflicting_reports`, `adversarial_notes`).
  - Trigger Second Emergency (contention demonstration).

### E4: Interactive Map Layer & Fleet Resource Grid
- **5-Zone municipal layout** (matches `Zone` enum): North, South, East, West, Central.
- Incident pins color-coded by priority/status (`CRITICAL` red, `HIGH` orange, `MEDIUM` yellow, `LOW` blue, `HOLD_FOR_HUMAN` purple, `REJECTED_INPUT` gray, `OVERRIDE_ACTIVE` cyan).
- Fleet resource inventory bar: Available vs Dispatched counts per `ResourceType` —
  `ambulance`, `fire_truck`, `police_unit`, `flood_response_unit`, `traffic_management_unit`.

### E5: Incident Inspection & Laya Advisory vs Guardrail Panel
- Deep inspection of selected incident:
  - Incident metadata: ID, zone, simulated time, report count, quality hints, raw notes.
  - Upstream ML Triad signals: Severity predictor (class + calibrated confidence), Traffic regressor (delta + interval confidence), Anomaly detector (data quality score + situational anomaly).
  - Laya Advisory block: suggested priority, answer confidence, probability distribution bars, recommended resource.
  - Final Policy Decision: final priority, decision state, assigned resources.
  - Guardrail divergence alert: `laya_guardrail_override` badge when Policy overrides or escalates Laya.
  - Structured matched rules (`R-LAYA-*`, `R-POLICY-*`) and structured reasons list.
  - Status indicators: `laya_ok`, `laya_unavailable`, `laya_timeout`, `laya_invalid_output`, `laya_fallback_used`, `laya_degraded`.

### E6: Zero-Trust Human Override & Real-Time Audit Viewer
- Override Modal/Form:
  - Required `operator_id` (non-empty string) and `reason` (enforces Invariant 7).
  - Override action selection from the frozen `OverrideType` enum: `CHANGE_PRIORITY`,
    `ASSIGN_RESOURCES`, `DISMISS_INCIDENT`, `ESCALATE_TO_HUMAN`, `MARK_DATA_UNTRUSTED`,
    `OVERRIDE_AUTOMATION_HOLD`.
  - Calls `POST /api/overrides`.
  - Visual indication on incident: `OVERRIDE_ACTIVE` with original automated decision displayed side-by-side.
- Real-time Audit Trail:
  - Live table/stream of entries from `GET /api/audit`.
  - Display actor, action, timestamp, before/after diff summary.
  - Inspection drawer showing full audit record including `AuditLayaMetadata` block and entry hash.
  - Hash chain status indicator.

### E7: What-If Counterfactual Sandbox Panel
- Sandbox controls: Scenarios `remove_one_ambulance`, `close_road`, `second_emergency`.
- Executes `POST /api/what-if/run` and displays stored result from `GET /api/what-if/{sandbox_id}/result`.
- Visual safety badges: `dry_run=true`, `audit_written=false`, `live_state_mutated=false`.
- Delta view: compares baseline live allocation vs counterfactual sandbox allocation.

### E8: Verification, Test Suite & Documentation
- Build verification: `pnpm run build` produces clean production bundle in `dashboard/dist`.
- End-to-end integration check: Python tests for CORS and API health; full model-free test suite (191+ tests).
- Update `docs/jevcity/ARCHITECTURE.md` (Command Center Dashboard section) and `README.md` with dashboard run instructions.
- Commit clean, push to `stage/phase5-dashboard`, open PR, verify CI.

---

## Deviation notes (audited 2026-10-07 against plan-of-record)

1. **Spec errors in this doc (corrected above):** E4 originally listed a 4-zone
   "Downtown" layout and Hazmat/Tow fleet types; E6 listed six override actions that do
   not exist in the repo. Implementation was always built against the frozen enums —
   only the doc text was wrong (fixed).
2. **Probability distribution:** plan-of-record requires it in the Laya UI; the frozen
   `DecisionRecord.laya` had no distribution field. Added additively:
   `LayaBlock.distribution: dict[str, float]` (populated from the normalized priority
   answer, `extra="forbid"` unchanged, schema exports regenerated,
   `tests/jevcity/test_laya_distribution.py`).
3. **Disable-Laya-advisory control:** no frozen endpoint can switch the adapter's
   runtime mode at request time. Implemented as a **display-only** hide/show toggle on
   the advisory card, explicitly labeled; policy authority and audit unaffected. Backend
   runtime mode switch remains out of scope under the frozen 16-route contract.
4. **Raw free-text notes:** `GET /api/incidents/{id}` does not return raw report notes
   (Inv-16 attack surface). Inspector shows ingestion `validation_status` as the quality
   hint instead; notes influence decisions through the pipeline only.
5. **Audit chain badge:** client cannot verify the hash chain (no frozen validate
   endpoint) — badge states `APPEND-ONLY • SHA-256 CHAINED` (schema fact), not a live
   "valid" verdict. Server-side validation stays in `validate_chain` / export CLI.
6. **Audit-write-failed state:** classified client-side on any HTTP 5xx
   (`AUDIT WRITE FAILED or server error`) since audit append failures surface as
   unhandled 500s; no dedicated endpoint exists under the frozen contract.
7. **What-If expired state:** surfaced via "Verify Stored Result (GET)" re-fetch — 404
   renders the `SANDBOX EXPIRED` badge.

## Status (2026-10-07)

- E1–E7 implemented (backend CORS + static mount, dashboard app, polling, map/inspector,
  override + audit, What-If). E8: `pnpm build` + `pnpm lint` green, tests
  `test_dashboard_phase5.py` + `test_laya_distribution.py` added, README/ARCHITECTURE
  updated. Remaining at audit: full-suite run, branch/PR/CI.
