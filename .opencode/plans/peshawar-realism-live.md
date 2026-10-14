# Plan: Visual Realism Pass + Peshawar Live Mode

Two workstreams, sequenced: **A) visual pass** (make dashboard look like a real ops console), **B) Peshawar live mode** (wire free real-world feeds, map zones to Peshawar areas). Decisions locked: Leaflet+OSM map, free no-key feeds only, 5-zone enum mapped to Peshawar areas (no schema churn).

## Constraints (repo rules — apply to every PR)

- No inline code comments; docstrings OK.
- Schemas additive-only (`extra="forbid"`) — new JSON Schema files OK, existing field removal forbidden.
- No host wall-clock in scoring/gates (live-mode timestamps are operational data, exempt — but eval/gates stay sim-clock).
- No new Python deps except possibly `httpx` promote-to-runtime (already in dev-deps). Frontend: `leaflet` + `react-leaflet` only.
- FROZEN_ROUTES ledger: new routes = additive, register in `docs/jevcity/API.md` + ledger.
- Seeds 42/7 for sim mode; live mode ignores seeds.
- Each workstream = its own PR chain, gated on full suite (337+) + frontend lint/build.

---

# Workstream A — Visual realism pass (PRs #33–#36)

## A1. Design foundation (PR #33) — tokens, type, layout shell

**Problem:** zero design tokens, 145× `font-mono`, no web font, `max-w-7xl` gutters on wide monitors, favicon mismatch, dead `animate-in` classes.

Changes:
- `dashboard/src/index.css` — add Tailwind v4 `@theme` block: operational palette (keep slate base; formalize accent tokens: `--color-crit`, `--color-warn`, `--color-info`, `--color-ok`, `--color-accent`), font tokens (`--font-mono` → JetBrains Mono web font via Google Fonts link in `index.html`; keep `ui-sans-serif` for prose).
- `index.html` — font preconnect + link; fix favicon (swap `#863bff` bolt to accent indigo/cyan matching header brand).
- `App.tsx` / `Header.tsx` — remove `max-w-7xl` constraint → full-width with sensible padding (`px-6 2xl:px-10`); sticky header stays.
- Kill dead `animate-in fade-in` ×3 → replace with Tailwind-native keyframes in `index.css` or opacity transitions.
- Status bar: move `ADIP v0.1.0` + `PORT 8200` + `Seeds: S:42/R:7` badges from Header into thin bottom status bar (footer, `text-[10px]`, dim) — header reserved for ops info. Seeds badge shown only in mock feed mode.

## A2. Real map — Leaflet + OSM (PR #34)

**Problem:** `MapLayer.tsx` = 5 rounded cards labeled "City Surveillance & Incident Zones" — biggest credibility gap.

Changes:
- Add `leaflet` + `react-leaflet` + `@types/leaflet` (dashboard only). No API key needed for OSM raster tiles (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`, attribution `© OpenStreetMap contributors`).
- New `dashboard/src/data/peshawar_zones.json` — 5 polygons + centroid per zone enum value (hand-drawn from OSM admin boundaries):
  - `central` = city core (Saddar, Khyber Rd, University Rd corridor)
  - `north` = Peshawar Cantt, Nowshera Rd axis, Kabul River north bank
  - `south` = Hayatabad, Bara road corridor
  - `east` = Mardan Rd, Charsadda Rd axis, Chamrani
  - `west` = Pabi, Shah Kas, Khyber Pass axis
- New `PeshawarMap.tsx`: dark-themed Leaflet map centered `34.008, 71.578`, zoom 12. Zone `<Polygon>` overlays tinted by live incident density (slate→amber→red). Incident markers (custom `DivIcon`: pulsing dot sized by priority). Unit markers from `/api/resources` (small squares colored by status: available emerald / assigned cyan / busy amber / offline slate). Dispatch animation: `FlightPill` replaced by polyline draw + marker fly-to (1.2s ease).
- `MapLayer.tsx` reworked: keeps fleet-pool bar; map replaces card grid. Zone + unit legends overlaid (absolute dim glass panels).
- Sim mode placement: incident pins at zone centroid + small deterministic jitter (incident_id hash) so pins don't stack. Live mode (B) uses true lat/lon.

## A3. Ops-console content pass (PR #35)

**Problem:** demo-harness noise in production UI; KPI strip thin; no incident age/ETA; hard-coded fake fallbacks in WhatIf.

Changes:
- `SimulationControls.tsx` → collapsible `DevDrawer` ("Simulation / Test Harness", collapsed by default). Keep all controls working; mock/cache/live selects + seeds + fault injection + sybil live inside. Command tab keeps: start/pause/reset, laya/vision mode selects, inject form (relabeled "Report Incident" — becomes real report entry in live mode).
- Strip "Invariant N" / "Phase 4" captions from `IncidentInspector`, `WhatIfSandbox`, `OverrideModal`, `SimulationControls`, `AuditTrail` → plain-language labels ("Multi-source corroboration", "Sandbox isolation", "Audit integrity: append-only · SHA-256 linked").
- `WhatIfSandbox.tsx` — delete hard-coded `'CRITICAL'/'AUTO_APPROVED'/'amb-01, pol-01'` fallback: render empty-state "Run a scenario to compare".
- `KpiStrip.tsx` — all 4 KPIs get sparklines (reuse `Sparkline`), delta arrow vs last poll, threshold tint (e.g. open incidents >10 amber).
- `IncidentInspector.tsx` — incident age (`now − first_seen`), assigned-unit ETA (zone-distance table), radio-log style recent-events list (last 3 decisions with timestamps).
- `VisionEvidence.tsx` — image thumbnail when `image_id` present: `<img src={/api/images/{id}/raw}>` (additive `GET /api/images/{image_id}/raw` if not existing — store already holds bytes). Upload → small "Attach evidence" button.
- `AuditChain.tsx` — replace literal `▼` glyphs with styled connector (`border-l` + chevron icon).
- `Header.tsx` — clock renders timezone suffix from `/api/state` (default `UTC (sim)`; `PKT` in live mode — prep for B3).

## A4. Realism verification (PR #36, small)

- Playwright screenshot pass (`webapp-testing` skill) at 1440p + 1920p: map renders, no dead space, drawer collapsed, fonts loaded.
- `pnpm lint`/`tsc`/`build`, full pytest (backend untouched except possibly images route), CI green, merge.

---

# Workstream B — Peshawar live mode (PRs #37–#40)

## B1. Feed infrastructure + zone config (PR #37)

**Backend seams (from exploration):**
- Cleanest injection: `SimulationState.append_replay(EventEnvelope)` (`jevcity/simulation/state.py:174-178`) — real coords/timestamps/source_ids, then `engine.process_pending()`.
- Clock: `SimClock.reset(start=...)` accepts arbitrary start (`simulation/clock.py:26`) → live mode resets to wall-clock UTC (operational timestamps only; gates/evals stay sim-clock).
- No background task host → new `feed_manager.py` daemon-thread pattern (same as `laya_adapter/adapter.py:254`).

Changes:
- `jevcity/schemas/enums.py` — additive: `FeedMode(mock | live)` enum (follows `LayaMode`/`VisionMode` pattern).
- New `jevcity/feeds/` package:
  - `base.py` — `FeedPoller` protocol: `poll() -> list[EventEnvelope]`; `FeedManager` daemon thread (30s cycle, jittered), per-feed last-good cache + failure counter (circuit-break after 3 fails, probe every 5th — mirror laya adapter).
  - `weather.py` — Open-Meteo: `GET https://api.open-meteo.com/v1/forecast?latitude=34.008&longitude=71.578&current=temperature_2m,precipitation,wind_speed_10m,weather_code` (no key). Maps weather_code → `context.weather` + flood-risk flag (heavy rain → synthetic `flood` suggestion in low-lying zone). 10-min poll.
  - `seismic.py` — USGS: `GET https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson`, bbox `[33.0–35.5N, 70.5–72.5E]`, M≥4.0 → honest mapping: `traffic_spike` event + notes "seismic event M{x} {dist}km" (IncidentType enum frozen). 5-min poll.
  - `gdacs.py` — GDACS: `GET https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=FL;EQ&alertlevel=orange;red` (geoJSON), distance filter → `flood`/context events. 30-min poll.
  - `reliefweb.py` — ReliefWeb: `GET https://api.reliefweb.int/v2/disasters?appname=jevcity-peshawar&filter[field][0]=country&filter[value][0]=Pakistan&limit=5` → situational advisories (NOT incidents; dashboard context strip). 60-min poll.
- `jevcity/config/peshawar_zones.json` + loader: per-zone polygon (same 5 polygons as frontend), centroid, unit-station coords (10 units at real stations: Rescue 1122 HQ Hayatabad, Cantt, etc.).
- `resource_pool.py` — add `PESHAWAR_FLEET` (17 units, callsigns `amb-hbt-01`, `pol-cnt-03`). `SimulationState.reset` gains optional `fleet` kwarg (default `_DEFAULT_FLEET` — zero test churn).
- `build_engine` / app lifespan: `JEVCITY_FEED_MODE=mock|live` env (default `mock` — existing behavior byte-identical). Live mode: `reset(start=datetime.now(UTC))`, `FeedManager.start(engine)`.
- New routes (additive, API.md + FROZEN_ROUTES ledger):
  - `GET /api/feeds` — mode, per-feed status (last poll, ok/fail, counts), weather snapshot.
  - `POST /api/feeds/refresh` — force one poll cycle (demo).
- `httpx` promoted dev→runtime (`pyproject.toml`) — only new dep.

## B2. Zone polygons + incident placement (PR #38)

- Live-mode incidents carry real `Location.lat/lon` from feed. `SimulationIncidentRequest` gains additive optional `lat`/`lon` (None default — fine under `extra="forbid"`).
- Frontend `PeshawarMap.tsx` already consumes lat/lon (from A2). Pins at true coords in live mode.
- `/api/resources` gains optional `lat/lon` (additive): live = station coords (static until real telemetry), sim = omitted (markers at zone centroid).

## B3. Live-mode dashboard affordances (PR #39)

- `Header` — live mode: wall-clock `Asia/Karachi (PKT)` from reset clock, cyan "LIVE" badge replaces "SIM", seeds hidden.
- New `ContextStrip.tsx` (command tab, under KPIs): weather chip, GDACS alert chip (orange/red if active), last ReliefWeb advisory (truncated + link). Dim when no data.
- Inject form in live mode = "Manual Report" (same validation + trust path — becomes 1122-calltaker entry).
- Sybil/second-emergency stay dev-drawer only.
- Honest labeling: persistent dim note in dev drawer + API.md: "Incident stream = live environmental feeds + manual reports; traffic synthetic (weather-modulated); Rescue 1122 CPS integration pending — no public API."

## B4. E2E verification + docs (PR #40)

- Integration tests (network-free CI): poller adapter unit tests with recorded fixtures (record once via `JEVCITY_FEED_RECORD=1`, commit under `datasets/jevcity/feeds/`); FeedManager start/stop/circuit-break; `/api/feeds` shape.
- `docs/jevcity/`: API.md (routes + env), USER_GUIDE.md (live mode), ARCHITECTURE.md (feeds diagram).
- Live smoke: `JEVCITY_FEED_MODE=live` uvicorn → weather chip populates, USGS real KP quakes (or honest "0 events"), PKT clock, audit chain verifies, mock-mode full suite still green.
- QA.md loop-7 row covering both workstreams.

---

# NOT in scope (explicit guards)

- No Rescue 1122 partnership/API (none public) — `feed_manager` pluggable so a CPS feed can drop in later.
- No real GPS telemetry (no source) — static station coords, honest.
- No live traffic API (none free for Pakistan) — synthetic traffic modulated by real weather + PKT hour-of-day; labeled.
- No zone enum rename (frozen, user-confirmed).
- No 3D/vector tiles, no chart-lib sprawl — hand-rolled viz stays (already credible per QA loops).
- No production auth/hardening — realistic ops-con *demo*, noted in docs.

# Execution order

```
A1 tokens/type/layout ──► A2 Leaflet map ──► A3 content pass ──► A4 verify
                              │
                              ▼ (map consumes lat/lon shape)
B1 feed infra + zones ──► B2 placement ──► B3 live dashboard UI ──► B4 E2E/docs
```

Strict serial for first two PRs, then A-stream/B1 can parallelize (different files; B1 backend-only).

# Risks

| Risk | Mitigation |
|---|---|
| OSM tile usage policy (heavy commercial traffic needs key) | Raster tiles fine for demo scale; attribution rendered; self-host tiles if scaled |
| USGS/GDACS downtime | Circuit-breaker (same as laya live); dashboard shows feed status honestly, never fakes green |
| Wall-clock vs "no host clock in scoring" rule | Wall clock only for live-mode operational timestamps; gates/evals always mock mode; CI runs mock only |
| Leaflet + React 19 compat | react-leaflet v5 supports React 19; pin; verify in A4 |
| Zone polygons wrong | Display-only (policy uses enum value, not geometry) — cosmetic, cheap fix |
| Schema drift | Additive-only enforced by existing export check; regenerate `schemas/*.json` per PR |

# Definition of done

1. Dashboard @1920p: full-width dark ops console, real Peshawar map, dim status bar, no demo-label noise, animations live.
2. `JEVCITY_FEED_MODE=live` → weather/seismic/GDACS drive real-context incidents at real coords, PKT clock, context strip populated; audit chain intact; `/api/feeds` health honest.
3. Default mock mode: 337+ suite green, byte-identical sim behavior.
4. CI green, all PRs rebase-merged, QA.md + API.md + USER_GUIDE.md current.
