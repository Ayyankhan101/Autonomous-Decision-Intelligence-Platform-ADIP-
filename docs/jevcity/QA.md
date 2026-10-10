# JevCity QA — test-loop findings and known limitations

Black-box + browser QA of the JevCity platform (API on :8200, Command Center
dashboard), run after Phase 6/7 integration. Method: seeded sessions (`42/7`),
payload fuzzing (~40 bad-request probes per loop), full UI sweeps in a real
browser with console monitoring, audit-chain and determinism checks after each
fix. Findings follow the project's rules: functional and data-integrity bugs get
fixed; cosmetic issues are logged but not fixed.

The loop stops after **two consecutive clean passes**.

## Loop log

| Loop | Result | Landed |
|---|---|---|
| 1 | 4 functional/data-integrity findings + 2 cosmetic | **PR #18** (`d6eb707`) |
| 2 | 2 functional findings + 1 cosmetic | **PR #19** (`e4b42f2`) |
| 3 (confirmation 1) | **CLEAN** — fuzz 0/0/0, all fixes hold, 0 console errors | — |
| 4 (confirmation 2) | **CLEAN** — fuzz 0/0/0 under rich state (7 incidents + sybil + second-emergency) | — |
| Post-audit | test hardening + determinism doc | **PR #20** (`b8b404b`) |
| Docs refresh | README graph, QA.md, count corrections | **PR #21** (`dcb276c`) |
| Backlog | 3 cosmetic findings + all known limitations cleared | **PR #22** (`9e003d0`) |

**Verdict: QA loop complete — 2 consecutive clean passes (loops 3 + 4).**

## Findings

| # | Surface | Finding | Severity | Status |
|---|---|---|---|---|
| F-B1 | dashboard | Incident "First seen" + audit timestamps rendered browser-local while header showed UTC — inconsistent clocks | functional (display) | Fixed (PR #18) |
| F-B2 | dashboard | Resource labels show `Flood Response_unit` — JS `.replace('_',' ')` replaces first underscore only (`MapLayer.tsx:253`, `IncidentInspector.tsx:98,356`) | cosmetic | Fixed (PR #22, `replaceAll` at all 5 label sites) |
| F-B3 | dashboard | Override modal had no max-height/scroll — on viewports ≤600 px the submit button sat below the fold with no scrollable ancestor | functional | Fixed (PR #18) |
| F-B4 | dashboard | "Verify Chain Now" appeared covered by sticky header | false alarm | scroll-position artifact, not a bug |
| F-B5 | dashboard | Audit chain view showed the **oldest** 8 entries labeled "last 8 of 19" — `AuditChain.tsx` `slice(-N)` assumed oldest-first while `/api/audit` returns newest-first | functional | Fixed (PR #18) |
| F-B6 | dashboard | "inc-00003 missing" after second-emergency | false alarm | id consumed by F-B7's incomplete rollback |
| F-B7 | engine | What-If `second_emergency` mutated live state then rolled back incompletely: sim clock ticked permanently, incident-id counter consumed (visible id gaps), `second_emergency_fired` left `True`. Violated `live_state_mutated=false` / Invariant 15 | data-integrity | Fixed (PR #18): `sandbox_scope()` context manager snapshots+restores clock, RNG streams, counters, pool, decision/history/validation collections, trust, audit count |
| F-B8 | dashboard | Overridden record shows `Final Decision Source: laya_proposed` while state is `OVERRIDE_ACTIVE` (field copied from original) | cosmetic | Fixed (PR #22, renders `override_active (original: …)`) |
| F-B9 | dashboard | "Incident notes" input (`SimulationControls.tsx:109,364`) accepts and stores `notes` but no UI surface ever displays them | cosmetic | Fixed (PR #22: additive `IncidentRecord.notes` + inspector "Notes:" row; display-only, Invariant 16 unchanged) |
| F-B10 | dashboard + API | Override modal sent `new_priority: CRITICAL` (state default) for **all** override types; server graded the stray priority as a raise, so a `DISMISS` on a life-safety incident was classified `BREAK_GLASS` at apply after the client had validated it as `HIGH` → 422 after client validation passed | functional | Fixed (PR #19): client sends `new_priority` only for `CHANGE_PRIORITY`; server normalizes in `assess_override`/`apply_override`; regression test `test_stray_new_priority_on_non_change_type_is_ignored` |
| F-B11 | engine | `POLICY_POSITION_SWITCHED` audit entry omitted `timestamp` → `log.py` fell back to host wall clock, mixing time bases inside one hash chain (violates "no host wall-clock anywhere") | data-integrity | Fixed (PR #19): entry stamped with `self.simulation.clock.now`; assertion in `test_policy_sandbox.py` |

### Designed friction (verified, not bugs)

- Re-override → 422 unless `break_glass=true`.
- Override audit entries reference the **original** decision id (asserted by `test_audit_phase4`).
- `HIGH` tier requires `impact_ack=true` + `context_code`; `BREAK_GLASS` requires `break_glass=true`; `CHANGE_PRIORITY` requires `new_priority`.
- `hazmat` is not a valid incident type (enum has 4: accident/fire/flood/traffic_spike) → 422.
- Field name is `reoptimise_active`, not `reoptimise` → 422.

### Verified clean (loops 3–4 + post-audit)

- Payload fuzz (fuzz_a/b/c): 0 errors, 0 unexpected 5xx across the whole session log.
- Negative paths: 409 (what-if with nothing decidable), 404 (unknown sandbox/decision/incident), 422 (enums, ranges, min-lengths), recording path traversal blocked (relative + absolute).
- Audit: chain intact, tamper detection covered by tests, newest-first rendering, sim-clock timestamps only (0 non-sim entries across 39), survives in-process reset, not cleared by reset.
- Determinism: same seeds + pinned policy position → byte-identical decisions across process restarts.
- What-If residue: zero after strengthening the residue snapshot (rng states, `_processed`, pool fingerprint, decision/history/validation sizes — PR #20).
- Resilience: backend kill → `BACKEND UNREACHABLE` banner → auto-recovery.
- Guardrail: 16 invariant tests; reset zeroes `_processed`; negative-path integrity counts/duplicates clean.
- Zero console errors in loops 1–4.

## Known limitations — all resolved (PR #22)

Originally logged as out-of-scope observations; cleared in the backlog pass:

1. **Concurrency** — `AuditLog.append` now serializes counter + `previous_hash`
   read-modify-write on a `threading.Lock` (test: 100 appends across 4 threads →
   unique ids, valid chain). Remaining: non-audit engine state is still shared
   without locks — acceptable for the single-operator demo.
2. **`sandbox_store` growth** — capped at 50 entries, oldest evicted
   (`test_sandbox_store_evicts_oldest_beyond_cap`).
3. **Persistence copy** — What-If footer now says "Recorded in session audit log ·
   cleared on restart" (matches the `:memory:` + RAM default).
4. **Cosmetic leftovers** — F-B2, F-B8, F-B9 fixed (see findings table).
