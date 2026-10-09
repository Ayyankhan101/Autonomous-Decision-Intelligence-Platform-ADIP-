# JevCity API (plan §5 — frozen endpoint list)

Base: `http://localhost:8200` · run: `uvicorn jevcity.api.app:app --port 8200`
JSON Schema exports (dashboard contract): `schemas/*.json` via `python -m jevcity.schemas.export`.

The 16 plan-frozen endpoints below are unchanged; two **additive** endpoints
were added: `POST /api/simulation/resume` (because `start()` resets state —
without it, pause → resume silently wiped the session) and
`POST /api/overrides/impact` (enhancement 4: read-only override risk preview).

## Reads

| Method | Path | Response model |
|--------|------|----------------|
| GET | `/api/state` | `StatePayload` — dashboard polls every 1–2 s |
| GET | `/api/incidents` | `IncidentListResponse` |
| GET | `/api/incidents/{incident_id}` | `IncidentResponse` (incident + validation + latest decision) |
| GET | `/api/decisions` | `DecisionListResponse` |
| GET | `/api/decisions/{decision_id}` | `DecisionRecord` (includes optional `lineage` block — evidence terms, decisive clause, expression; enhancement 3) |
| GET | `/api/resources` | `ResourceListResponse` |
| GET | `/api/audit?limit=100` | `AuditListResponse` |

## Simulation controls

| Method | Path | Body |
|--------|------|------|
| POST | `/api/simulation/start` | `{session_seed, scenario_seed, recording?, speed?}` — `recording` = JSONL filename under `datasets/jevcity/` streams the recording through the live pipeline (sync; `speed` reserved for live pacing) |
| POST | `/api/simulation/pause` | — |
| POST | `/api/simulation/resume` | — continue current session **without** reseed/clear (`start` resets — additive extension fixing pause/resume data loss) |
| POST | `/api/simulation/reset` | `{session_seed, scenario_seed}` |
| POST | `/api/simulation/incident` | `{incident_type, zone, severity?, source_id?, notes?, multi_report?}` |
| POST | `/api/simulation/bad-data` | `{mode: missing_fields\|out_of_range\|conflicting_reports\|adversarial_notes, target_incident_id?}` |
| POST | `/api/simulation/second-emergency` | `{incident_type?, zone?}` |

All control responses: `SimulationActionResponse {ok, incident_id, decision_ids}`.

## Governance

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/overrides` | `OverrideRequest` — `operator_id` and `reason` required (**422** if empty, Invariant 7). Additive optional fields (enhancement 3): `cited_clause` (clause id or gap marker), `reason_code` (`POLICY_CLAUSE\|POLICY_GAP\|EXTERNAL_CONTEXT`) — both stored on the override record and the audit entry; API stays backward-compatible, dashboard enforces selection. Enhancement 4 friction: server classifies each override into `impact_tier` (`LOW\|HIGH\|BREAK_GLASS`); `HIGH` requires `impact_ack=true` + `context_code`, life-safety priority raises are `BREAK_GLASS` and require `break_glass=true` (each missing → **422**); `LOW` needs no extra fields. Tier, `context_code`, `break_glass` stored on record + audit entry |
| POST | `/api/overrides/impact` | `ImpactPreviewRequest` → `ImpactPreviewResponse` — dry run, never mutates state/audit; returns `tier`, human-readable `warning` with projected impact (zone, priority delta, available recommended units), and `requires_*` flags the UI turns into controls (**404** unknown decision) |
| POST | `/api/what-if/run` | `WhatIfRequest {scenario: remove_one_ambulance\|close_road\|second_emergency}` → `WhatIfResult` |
| GET | `/api/what-if/{sandbox_id}/result` | stored sandbox result |

What-If results always carry `dry_run=true, audit_written=false, live_state_mutated=false`.

## Polling payload (`GET /api/state`)

```json
{
  "simulated_time": "2026-09-27T10:00:00+00:00",
  "running": true,
  "session_seed": 42,
  "scenario_seed": 7,
  "incident_count": 3,
  "decision_count": 3,
  "open_incident_count": 3,
  "available_resources": {"ambulance": 5, "fire_truck": 3, "...": 0},
  "laya_mode": "mock",
  "last_laya_status": "ok"
}
```

## Errors

- `404` unknown incident/decision/sandbox/override target
- `409` What-If with no incidents yet
- `422` schema violations (empty override actor/reason, bad enums, out-of-range fields)

## Dashboard UI states (contract for Phase 5 React build)

`laya_unavailable · laya_timeout · laya_invalid_output · laya_blocked_by_policy ·
laya_fallback_used` — derived from `decision.laya.status` + `matched_rules`
(`R-LAYA-*` prefixes) + `final_decision_source`.
