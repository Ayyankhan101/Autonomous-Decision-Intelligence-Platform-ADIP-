# Vision Evidence Pipeline — design spec

Date: 2026-10-10
Status: approved (brainstorming session, user-approved approach A)
Scope: shared `vision/` component consumed by JevCity and ADIP

## Problem

The platform is text/structured-data only. There is no image handling anywhere
in the repo: incidents are structured events (`schemas/event.py`), free text is
bounded and kept out of the Laya state (Invariant 16), and Laya itself has a
~512-token text context. Users want to attach image data (e.g. an accident
scene photo or a support-ticket screenshot) and have the system work from it.

## Goal

Upload an image, extract **structured facts** with a local vision model, and
use those facts as **evidence, not authority**: a new report source that the
validator can soft-flag on, the dashboard can display, and the audit chain can
record — without changing the guardrail, the ML triad, or the
"Laya proposes, policy decides" split.

## Decisions (user-confirmed)

1. **Role:** vision → structured facts (not display-only, not direct classification).
2. **Consumers:** both JevCity incidents and ADIP tickets, via one shared component.
3. **Runtime:** local MLX VLM (`mlx-vlm`, e.g. Qwen2.5-VL-3B) — keeps
   "nothing leaves the box", $0 marginal cost.
4. **Influence:** evidence, not authority — soft flags + display + audit only.
5. **Surface:** API endpoints plus dashboard upload controls in both UIs.
6. **Approach:** A — extraction pipeline with `mock | cache | live` modes
   mirroring the existing `LayaAdapter`. Extraction runs **synchronously inside
   the upload request** (instant for mock/cache; ~1–3 s for live, acceptable for
   a human-initiated upload); `GET /facts` exists so other consumers and the
   dashboard can retrieve facts without re-uploading.

## Architecture

### Shared package `vision/` (repo root)

| Unit | Purpose |
|---|---|
| `vision/schema.py` | `VisionFacts` (Pydantic): `image_sha256`, `scene` enum (accident/fire/flood/traffic/other/unknown), `objects` (bounded list), `damage_severity` (low/medium/high/unknown), `injuries_visible` (bool/unknown), per-field confidence values, `model_id`, `model_version`, `mode`, `latency_ms`, `status` (`OK` \| `UNAVAILABLE` \| `INVALID_RESPONSE`). |
| `vision/analyzer.py` | `VisionAnalyzer` — clone of `LayaAdapter` semantics: modes `mock \| cache \| live`, fail-closed, lazy model load inside a daemon timeout thread (`LIVE_TIMEOUT_S`, `LIVE_MAX_ATTEMPTS=2`), `health()`. **mock:** deterministic facts derived from the image sha256 — no model needed; seeded demos stay byte-identical and the default test suite stays model-free. **cache:** in-process dict keyed by sha256. **live:** `mlx-vlm` real inference (~1–3 s/image on M1 Pro). |
| `vision/store.py` | Content-addressed image storage: bytes on disk keyed by sha256 under `datasets/vision/images/` (gitignored — runtime uploads) + in-process metadata registry capped like `sandbox_store` (oldest evicted). |

`mlx-vlm` is an **optional dependency**: required only for live mode; mock and
cache modes run with no vision packages installed.

### Schemas and routes

New request/response models exported to JSON Schema via
`python -m jevcity.schemas.export` (JevCity side) alongside the existing set.

**JevCity — 4 new additive routes (22 → 26; all existing routes untouched):**

| Route | Purpose |
|---|---|
| `POST /api/images` | upload image bytes (MIME-sniffed, ≤ 5 MB) → sha256, store, run `VisionAnalyzer.analyze()` synchronously, return `image_id` + facts (`status: OK`/`UNAVAILABLE`/`INVALID_RESPONSE`) |
| `GET /api/images/{image_id}/facts` | retrieve facts when ready (dashboard polls) |
| `POST /api/incidents/{incident_id}/images` | attach an uploaded image to an incident → `vision` block on the incident record (avoids modifying the frozen `POST /api/simulation/incident` contract) |
| `POST /api/vision/mode` | hot-swap `mock \| cache \| live`, mirroring `POST /api/simulation/laya-mode` |

**ADIP — 1 new route + 1 optional field:**

- `POST /images` — same upload + extract shape as JevCity's.
- `POST /decide` gains an **optional** `image_ids: list[str]` field (default
  empty → existing contract and tests unchanged). Referenced facts ride into
  the explanation and audit record as evidence; routing gates are unaffected.

### Dashboard

- **JevCity Command Center:** upload control in the incident inspector; a
  "Vision evidence" card showing facts, per-field confidence, model/mode badge,
  and status; `/api/images` joins the existing 1.5 s poll set.
- **ADIP ticket form:** simple attachment control showing extracted-facts
  summary alongside the decision explanation.

## Data flow

```text
upload → sha256 → store bytes → VisionAnalyzer.analyze()
   mock:  instant, deterministic from sha       → facts OK
   cache: hit → facts; miss → live (or UNAVAILABLE when no model)
   live:  lazy-load mlx-vlm in timeout thread   → facts OK / UNAVAILABLE / INVALID_RESPONSE

POST /api/incidents/{id}/images → vision block attached to incident record

next process_pending():
   validator compares vision facts vs reported attributes
     (report says minor, vision sees high damage → soft ValidationFinding
      code `severity_mismatch_vision`, using the existing soft-flag machinery)
   facts recorded on the decision record + audit entry (image sha, model,
     mode, per-field confidence) — guardrail and ML triad unchanged

dashboard polls → vision evidence card beside the Laya/policy split
```

In v1 the vision block is a **report source only**: soft flags, display, audit.
No ML retraining and no direct severity writes.

## Determinism and audit

- Mock mode derives facts purely from image bytes → same upload, same facts;
  seeded demos remain byte-identical across restarts.
- Live facts are stamped with `model_id` + `model_version` + `latency_ms`.
- Facts are immutable once analyzed; a mode switch affects only new uploads.
- Audit entries use the existing `payload_hash()` hash-stability rule, so the
  new vision payload fields cannot invalidate old chain rows.

## Error handling

| Failure | Behavior |
|---|---|
| Bad upload (MIME sniff mismatch, corrupt bytes, > 5 MB) | 422 with structured detail, matching existing validation style |
| Model unavailable / timeout / crash (live) | `status: UNAVAILABLE`; `vision_status` recorded on incident + audit; incident processing **proceeds text-only** (absent evidence never blocks a decision) |
| Malformed model output | `INVALID_RESPONSE` — fail-closed to "no facts", never guessed fields |
| Attach to unknown incident | 404 (edge-coverage conventions) |
| Mode switch mid-session | Allowed (like `laya-mode`); analyzed images keep recorded facts |

## Testing

- **Model-free (default suite):** mock-analyzer determinism, mode switching,
  cache keying, store cap eviction; upload 422 battery; attach 404/409; facts
  retrieval; `/decide` with/without `image_ids`; validator soft-flag raised on
  mismatch and absent on agreement; vision block present in audit with valid
  chain; dashboard facts-card/upload-error rendering.
- **Model-marked:** 1–2 live smoke tests (`@pytest.mark.model`, deselected by
  default like the existing model tier) analyzing a committed fixture image
  with the real mlx-vlm model.
- **Fixtures:** two small committed images under `fixtures/vision/` (a
  synthetic scene PNG + an invalid file).
- Route-count, README, and CI test-count updates land in the docs step.

## Out of scope (v1)

- Video, batch upload, image generation, cloud vision fallback.
- ML-triad retraining on vision features (explicitly declined: no direct override).
- Auth changes (single-operator MVP posture).
- Calibration/eval-gate work for vision on the ADIP side.

## Rollout order

1. `vision/` core (schema → mock analyzer → store) + unit tests
2. JevCity routes + attach/validator/audit + dashboard card
3. ADIP `POST /images` + `/decide.image_ids` + tests
4. Live mlx-vlm mode behind the optional dependency + model-marked smoke tests
5. Docs (README counts/endpoints, ARCHITECTURE.md, API.md, GUARDRAIL.md
   soft-flag row if needed) → branch + PR per main-protection rules
