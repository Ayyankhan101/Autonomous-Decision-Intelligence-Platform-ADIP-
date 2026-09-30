# Phase 4 — Human Override & Audit Layer (plan §Phase 4)

Source: `JevCity_Implementation_Plan_Revised_v2_Laya.docx` Phase 4 (weeks 5–7).
Branch: `stage/phase4-override-audit`. Execution: in-session (delegate_task broken — ledger deviation stands).

## Current state (Phase 0–2 already shipped)

- `AuditEntry` + hash chain (`previous_hash`/`entry_hash`), DB triggers block UPDATE/DELETE,
  dry-run rejection — `jevcity/audit/log.py`, `tests/jevcity/test_audit.py`
- `AuditLayaMetadata` on every DECISION_EMITTED entry (checkpoint, router, status,
  state/questions hash, suggested priority, AC, latency, guardrail_applied)
- Override workflow: `POST /api/overrides`, Inv-7 422s (operator_id + reason required),
  `OverrideType` 6 values, new OVERRIDE_ACTIVE record keeps original decision
- Viewer: `GET /api/audit` (16-endpoint contract frozen — no new endpoints)

## Gaps → tasks

- **D1 audit metadata completeness** — `AuditLayaMetadata` += `laya_questions_version`
  (const `QUESTIONS_VERSION="q-0.1.0"` exists in `questions.py`, never stored),
  `laya_final_decision_source`, `laya_fallback_used` (status != OK),
  `laya_guardrail_modified` (source == POLICY_FINALIZED; LAYA_PROPOSED → False;
  no suggestion → None) — plan: "store whether guardrails modified the suggestion,
  whether fallback was used". Populate in `_append_audit`.
- **D2 override entry carries Laya metadata** — `apply_override` audit.append currently
  omits `laya=` → plan test "human override after Laya recommendation is auditable" fails.
  Pass `original.laya` block.
- **D3 schemas export** — audit_entry.json freshness (`uv run python -m jevcity.schemas.export`).
- **D4 audit tests (plan list)**
  - no API route mutates audit rows (routes with `audit` are GET-only; full route set == frozen 16)
  - original automated decision still visible after override (GET by original id)
  - Laya TIMEOUT / INVALID_RESPONSE statuses auditable (force_status adapter)
  - guardrail-modified suggestion auditable (fake upstream MEDIUM vs final HIGH →
    source=policy_finalized, guardrail_modified=True) — reuse C8 fake pattern
  - fallback used auditable (live RuntimeError → fallback_rule, fallback_used=True)
  - human override after Laya recommendation auditable (OVERRIDE_APPLIED entry has
    operator, reason, laya metadata)
  - audit `laya_state_hash` == decision `laya.state_hash`
  - questions version recorded == `QUESTIONS_VERSION`
  - hash chain still validates with Laya-bearing entries (append-only preserved)
- **D5 audit export** — CLI `tools/export_audit.py` (JSONL dump from sqlite file path;
  refuse `:memory:` with clear error) + test on tmp db. No new API endpoint (frozen 16).
- **D6 docs** — ARCHITECTURE §Audit: operator identity model (operator_id = opaque
  non-empty string, actor `system` reserved, no authn in MVP), export tool pointer,
  audit guarantees (triggers + hash chain + route absence).

## Constraints (standing)

No inline comments; ruff E9,F len 100; schemas additive-only extra=forbid; 16 endpoints
frozen; no host wall-clock in features/labels; all gates/tests honest; commit messages
normal prose; land via branch → PR → green → rebase-merge.

## Exit

ruff + full model-free suite green; PR merged; post-merge main CI green (unit + macos
incl. laya_live smoke); ledger closed; stage branch deleted.
