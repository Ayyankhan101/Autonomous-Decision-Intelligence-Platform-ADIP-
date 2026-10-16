# 3D Agent Topology View (Workstream C) — Plan

Branch: `feat/c1-3d-topology` → PR #41 (single PR unless it balloons).

## Decisions (user-confirmed)

- **Data**: real ADIP backend (`/api/dashboard` bundle — no extra polling; reuse App's existing hook).
- **Mount**: 4th tab `Topology` in Header, lazy-loaded (`React.lazy` + Suspense) so three.js (~600 KB gz) only downloads on open.
- **Layout**: split files per repo convention (not single-file).

## New dependencies (React 19.2.8 compatible)

```
three, @react-three/fiber@^9 (peer react >=19 <19.4 ✓), @react-three/drei@^10, zustand@^5
```

## Backend → 3D agent mapping (adapter in store)

| 3D concept | Real backend source |
|---|---|
| Agent node (octahedron) | `/api/resources` — 16 mock units / 17 Peshawar units (live) |
| Agent status color | `Resource.status`: available=emerald, assigned=cyan, busy=amber, offline=slate |
| `processing_load` (derived) | available=15%, assigned=55%, busy=85%, offline=0% + ±5% jitter on tick (visual only) |
| `current_task` | `assigned_incident_id` → incident type/zone from `/api/incidents` |
| `decision_confidence` | latest decision with this unit in `assigned_resource_ids` → `overall_confidence × 100` |
| Incident marker (small icosahedron) | open incidents; color = decision priority |
| Assignment edge | decision.assigned_resource_ids unit → incident |
| Pipeline edges (pulse flow) | animated dashed lines along assignment edges; speed × simSpeed |
| Event log lines | real tail of `/api/decisions` + `/api/audit` (timestamp, id, priority, state, source) |
| "Inject Malicious Anomaly" | `POST /api/simulation/bad-data {mode: "adversarial_notes"}` (409 if paused → toast honest error) |
| "OVERRIDE DECISION" | `POST /api/overrides/impact` preview → if tier allows, `POST /api/overrides` (`operator_id: "topology-hud"`, reason required, CHANGE_PRIORITY / OVERRIDE_AUTOMATION_HOLD) |
| "TERMINATE NODE" | **visual-only flag** + dim tooltip: "no CPS teardown API — Rescue 1122 integration pending" (honest labeling, no fake green) |
| Clock / FPS / compute load | FPS from R3F `useFrame` delta; compute load = mean derived processing_load; clock = `state.simulated_time` (PKT in live) |

Zone-based layout: agent rest positions from `lat/lon` (B2) projected to XZ plane around Peshawar center, y = small per-type offset. Mock-mode units (no lat/lon) placed on a ring by zone angle.

## Files

```
dashboard/src/stores/topologyStore.ts     — zustand: agents (adapter output), logs ring (200),
                                             selectedAgentId, simSpeed, anomalyFlash ids,
                                             setFromDashboard(bundle), actions
dashboard/src/components/topology/Scene.tsx      — Canvas content: Grid, Lights, AgentNodes,
                                                   IncidentNodes, AssignmentEdges (animated),
                                                   OrbitControls, hover glow, click select
dashboard/src/components/topology/Hud.tsx        — header panes (core status, runtime, FPS, load),
                                                   LeftMatrix, TelemetryPanel (slide-in), BottomTicker
dashboard/src/components/topology/AgentTopology3D.tsx — ErrorBoundary + Suspense + Canvas + wiring
dashboard/src/App.tsx          — 'topology' tab + lazy import
dashboard/src/components/Header.tsx — 4th tab button (Network icon)
dashboard/src/types/topology.ts — TopologyAgent, LogLine, TelemetryView types
```

## Scene specifics

- `<Canvas camera={{position:[0,18,22], fov:50}}>` + `<color attach="background" args={['#0b0f19']}/>`.
- `InfiniteGrid` (drei) + faint fog.
- Agents: `octahedronGeometry(0.55)`, `meshStandardMaterial` emissive by status, intensity pulses with processing_load; hover → emissive boost + scale 1.15 (no Outline pass needed — cheap + clean); selected → rotating ring (torus).
- Incidents: icosahedron(0.3), color by priority, slow spin.
- Edges: `<Line>` (drei) with `dashed`, animated `dashOffset` in `useFrame` × simSpeed; edge color = decision state.
- Anomaly flash: store sets `anomalyFlash: incident_id` → node turns rose 2s.
- All geometry/materials via JSX (auto-dispose on unmount); no manual BufferGeometry leaks.

## HUD specifics

- Glassmorphism: `bg-slate-900/80 backdrop-blur-md border border-cyan-500/30` (matches spec + existing theme).
- Left matrix: compact rows `[id] • [status pill] • [confidence%] • [load bar]`; click row selects node too.
- Right panel slides in on selection: task, load, confidence, zone, last decision (priority/state/latency), OVERRIDE button (impact preview first), TERMINATE (disabled + honest tooltip).
- Bottom: scrolling log (newest top, monospace, colored by level) + speed buttons 1x/2x/4x + pause (pauses local metric jitter only — honest label "visual sim"; backend sim pause stays in Command tab) + Inject Anomaly button.
- Null-safety: no selected agent → panel unmounted; bundle null → full-canvas "AWAITING TELEMETRY" dim state.

## Quality gates

- `npm run build` (tsc -b) clean, `npm run lint` clean.
- Manual: tab open, hover/click nodes, override flow on a running mock sim, anomaly inject, 0 console errors, lazy chunk separate.
- No backend changes; no FROZEN_ROUTES impact (uses existing routes only).
- Backend running check: if `/api/dashboard` fails → existing UNREACHABLE banner already handles; topology shows awaiting state.

## Out of scope

- Real GPS movement (static coords per B2 honesty note).
- WebGPU / postprocessing bloom (keep budget lean; emissive + fog sells it).
- Backend "terminate" API (none exists; visual-only honest).
