# JevCity Command Center Dashboard (Phase 5)

React + TypeScript + Vite + Tailwind front end for the JevCity API (port 8200).

## Views

- **Command Center** — 5-zone map with severity-colored incident pins, fleet availability
  bars, incident inspector (upstream ML triad signals, Laya advisory vs deterministic
  policy split with divergence alert, matched rules, resource assignments), simulation
  controls (start/pause/reset with seeds, inject incident, inject bad data, trigger
  second emergency), human override modal (operator + reason enforced).
- **What-If Sandbox** — counterfactual scenarios with `dry_run` / `audit_written=false` /
  `live_state_mutated=false` badges, delta vs live baseline, stored-result re-fetch
  (renders `SANDBOX EXPIRED` on 404).
- **Audit Trail** — live `GET /api/audit` stream with actor/action/before-after, full
  Laya metadata block, entry and previous hashes.

## Run

```bash
pnpm install
pnpm dev        # http://localhost:5173, proxies /api → http://localhost:8200
pnpm build      # production bundle → dist/ (served by the API at /)
pnpm lint       # oxlint
```

The API mounts `dist/` at `/` when it exists (`StaticFiles`), so a plain
`uvicorn jevcity.api.app:app --port 8200` serves the built dashboard with no extra
process. Route set stays frozen at 16 — the mount never adds `/api/*` routes.

Types in `src/types/api.ts` mirror `schemas/*.json` (additive-only contract).
