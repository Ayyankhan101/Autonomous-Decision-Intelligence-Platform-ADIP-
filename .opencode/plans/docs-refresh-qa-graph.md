# Docs refresh + README JevCity graph + QA.md

Branch: `docs/refresh` → PR → merge (main-protection requires PR).
Source of truth: repo state at `b8b404b` (QA loops 1–4 complete, 304 tests, 22 routes).

## 1. README.md

- **Status line (5)**: "Phase 0 built and measured" → phases 0–7 built (pipeline, eval, JevCity vertical slice, dashboard, demo) + QA loops 1–4 (2 clean passes, PRs #18–20). Keep blueprint pointer.
- **JevCity section (9–38)**: refresh bullets — 22 endpoints (16 frozen + 6 additive), E1–E4 enhancements (trust/sybil, policy sandbox, lineage, override friction) + demo-liveness (audit verify, laya-mode hot-swap), QA verified; docs list add `QA.md`.
- **New graph** (user choice: JevCity architecture flowchart): mermaid graph in JevCity section —
  ```
  seeded SimClock(42/7) → validate[hard-reject/soft-flag] → features → ML triad
  (severity/traffic/anomaly) → Laya adapter (mock|cache|live, fail-closed)
  → guardrail (16 invariants, precedence order) → greedy allocate → decision record
  → append-only hash-chain audit (audit/verify)
  side: overrides (friction tiers LOW/HIGH/BREAK_GLASS) + policy position (reoptimise)
  side: What-If sandbox (dry-run, zero live writes)
  presentation: FastAPI :8200 (22 routes) ↔ React dashboard (1.5 s poll)
  ```
  Style matches existing README graphs (`classDef` stage/decision colors).
- **Test counts** ×3 (lines 297 CI, 304 build, 334 tests/): 58 → **304** model-free (+ note `pytest -m model` / `laya_live` 3).
- Roadmap: no structural change.

## 2. docs/jevcity/API.md

- Prose (6–16): "six additive" enumerates only 5 → add sybil sentence (enhancement 1, fake-identity reports 2–10) so count matches. Rows already correct.

## 3. docs/jevcity/ARCHITECTURE.md

- **Route-freeze wording** ×3 (121–122, 135, 148): "frozen at 16 / contract frozen at 16" → "16 plan-frozen routes unchanged; 6 additive extensions (resume, overrides/impact, policy/position, audit/verify, laya-mode, sybil) = 22 total, ledger `tests/jevcity/test_audit_phase4.py::FROZEN_ROUTES`".
- **New sections** after "Decision authority":
  - **E1 trust scoring** — per-stream veracity, `R-TRUST-DOWNWEIGHT-01`, sybil endpoint (GUARDRAIL.md, test_trust.py).
  - **E2 policy position sandbox** — RESPONSE_TIME/EQUITY/ECO, `reoptimise_active`, `POLICY_POSITION_SWITCHED` on sim clock, **runtime config persists across start/reset** (pin position for determinism).
  - **E3 decision lineage** — evidence terms / decisive clause / expression on `GET /api/decisions/{id}` (test_lineage.py).
  - **E4 override friction** — tiers LOW/HIGH/BREAK_GLASS, required flags, `new_priority` only for CHANGE_PRIORITY (test_friction.py).
  - **Demo-liveness** — `/api/audit/verify`, `/api/simulation/laya-mode`.
- **Seeding**: append policy-persistence determinism note (QA finding).
- **What-If**: upgrade to `sandbox_scope()` semantics — restores clocks, RNG stream states, generator counters, pool fingerprint, decision/history/validation sets, trust scores, audit count; ids `sbx-*`; second-emergency registry rollback.
- **Audit**: `GET /api/audit` newest-first; sim-clock timestamps (QA loop 2); audit survives in-process reset, not cleared (immutable).
- **Tests map**: add test_trust, test_policy_sandbox, test_friction, test_lineage, test_edge_coverage, test_liveness, test_demo_script, test_replay, test_features, test_ml_dataset/test_ml_models, test_wrapper.

## 4. docs/jevcity/QA.md (new)

Check `/tmp/qa-jevcity/findings.md` into repo, structured:

- Scope + method (API black-box fuzz, browser console, seeds 42/7, gates per loop).
- Loop log: loop 1 (4 findings → PR #18 `d6eb707`), loop 2 (2 → PR #19 `e4b42f2`), loops 3+4 clean → stop; audit-hardening PR #20 `b8b404b`.
- Findings table F-B1…F-B11: title, severity, fix commit.
- Verified-clean list (negative paths, tamper detection, residue, determinism).
- Known limitations (by scope): concurrency (no locks — single-operator safe), `sandbox_store` unbounded growth, audit `:memory:` default vs "persisted" UI copy, cosmetic F-B2 + F-B9.

## 5. Light passes (factual drift only)

- **DEMO_RUNBOOK/DEMO_BEATS**: verify no stale pre-fix UI text (UTC timestamps, modal scroll); touch only if wrong.
- **GUARDRAIL.md**: E1 rule ✓; add E4 friction row only if absent.
- **PHASE0_SIGNOFF / ERRATA / CHECKPOINT_CARD / LAYA_* / STATE_BUILDER / CONFIDENCE / PROFESSIONAL_PRACTICES**: point-in-time — no edits unless hard factual contradiction.

## 6. Verification + landing

1. `ruff check .` + `pytest -q -m "not model"` (expect 304).
2. `pnpm build` + `npx oxlint`.
3. Mermaid: no new deps (no mermaid-cli) → manual syntax, reuse proven patterns from existing README graphs.
4. Branch `docs/refresh`, normal-prose commit, push, `gh pr create --body-file`, CI green, `gh pr merge --rebase --delete-branch`.
5. Copy findings.md into QA.md before /tmp cleanup.
