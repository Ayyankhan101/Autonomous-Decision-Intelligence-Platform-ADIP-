# Vision Evidence Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users upload image data; a local MLX vision model extracts structured facts (`VisionFacts`) that attach to JevCity incidents and ADIP tickets as auditable evidence (soft flags + display), never overriding the guardrail or ML triad.

**Architecture:** New shared `vision/` package (schema → content-addressed store → `VisionAnalyzer` with `mock | cache | live` modes cloned from `LayaAdapter`). JevCity gets 4 additive routes (22 → 26, route-ledger test updated) plus `IncidentRecord.vision` and a `VISION_ATTACHED` audit entry written with the sim clock. ADIP gets `POST /images` plus optional `/decide.image_ids`; evidence rides in the explanation and a new `vision_json` audit column without touching `decision_json` (replay stays bit-for-bit).

**Tech Stack:** Python 3.11+ / FastAPI / Pydantic v2 / uv / pytest (mock by default; `model` marker for live smokes); React + TS + Vite + Tailwind dashboard (pnpm, oxlint); optional extra `mlx-vlm` for live mode.

**Spec:** `docs/superpowers/specs/2026-10-10-vision-evidence-design.md` (authoritative for scope decisions).

## Global Constraints

- The 16 plan-frozen JevCity routes are never modified; vision adds **4 new additive routes only**. Ledger: `tests/jevcity/test_audit_phase4.py::FROZEN_ROUTES` must be extended (it is asserted with `==`).
- Schemas are **additive-only** with `model_config = ConfigDict(extra="forbid")`. After any schema change run `uv run python -m jevcity.schemas.export` and commit `schemas/*.json` (freshness asserted by `tests/test_schemas_export.py`).
- **No host wall-clock in domain logic.** Audit entries from the engine pass `timestamp=self.simulation.clock.now`. `VisionFacts`/`ImageMeta` carry **no wall-clock timestamps** (latency_ms only).
- **Evidence, not authority:** no vision code may write severity, touch the ML triad, or enter the Laya state (Invariant 16). The only lever is the existing soft-flag mechanism (`ValidationFinding(severity="soft", ...)`).
- **Determinism:** mock-mode facts derive only from image bytes → byte-identical across restarts.
- **Fail-closed:** live failures produce `VisionStatus.UNAVAILABLE` / `INVALID_RESPONSE`; a decision with unavailable facts proceeds text-only.
- Default test tier stays model-free: `pytest -q -m "not model"` (pytest `addopts` already deselects `model`).
- Ruff: line-length 100, `select = ["E9", "F"]`. Run `uv run ruff check .` after every Python task.
- Image transport is **JSON base64** (no `python-multipart` dependency): `image_b64` max 7_000_000 chars, decoded payload max 5_000_000 bytes, MIME by magic bytes (PNG/JPEG/WebP only).
- Branch for landing: `feature/vision-evidence` → PR → merge (main-protection requires PR; never push to main).

## File Structure

**Create:**
- `vision/__init__.py` — package exports
- `vision/schema.py` — `VisionFacts`, enums, `UploadRequest`/`UploadResponse`/`FactsResponse` (shared by both apps)
- `vision/store.py` — `ImageStore`, `sniff_mime`, `MAX_IMAGE_BYTES`
- `vision/analyzer.py` — `VisionAnalyzer` (mock/cache/live), `VISION_MODEL_ID`
- `jevcity/schemas/vision_api.py` — JevCity-only request/response models + `VisionAttachment`
- `jevcity/ingestion/vision_findings.py` — `vision_findings()` pure function
- `dashboard/src/components/VisionEvidence.tsx` — upload control + facts card
- `tests/vision/test_schema.py`, `tests/vision/test_store.py`, `tests/vision/test_analyzer.py`, `tests/vision/test_live.py`
- `tests/jevcity/test_vision_api.py`, `tests/test_vision_adip.py`
- `fixtures/vision/scene.png`, `fixtures/vision/not-image.txt`

**Modify:**
- `jevcity/schemas/__init__.py`, `jevcity/schemas/resources.py` (`IncidentRecord.vision`), `jevcity/schemas/export.py`
- `jevcity/decision_engine/engine.py` (`attach_image()`)
- `jevcity/api/app.py` (4 routes + app-owned analyzer/store)
- `tests/jevcity/test_audit_phase4.py` (`FROZEN_ROUTES` += 4)
- `serving/app.py` (`POST /images`, `DecideRequest.image_ids`), `serving/pipeline.py` (vision column + evidence suffix)
- `dashboard/src/types/api.ts`, `dashboard/src/services/api.ts`, `dashboard/src/components/IncidentInspector.tsx`
- `pyproject.toml` (wheel packages + `vision` extra), `.gitignore`
- Docs: `README.md`, `docs/jevcity/API.md`, `docs/jevcity/ARCHITECTURE.md`

---

### Task 1: `vision/schema.py` — facts + shared upload contracts

**Files:**
- Create: `vision/__init__.py`, `vision/schema.py`
- Test: `tests/vision/test_schema.py`

**Interfaces:**
- Produces: `VisionFacts`, `VisionStatus`, `VisionMode`, `SceneType`, `DamageSeverity`, `UploadRequest`, `UploadResponse`, `FactsResponse` — consumed by every later task.

- [ ] **Step 1: Write the failing tests**

```python
# tests/vision/test_schema.py
from vision.schema import (
    DamageSeverity, SceneType, UploadRequest, VisionFacts, VisionMode, VisionStatus,
)


def test_vision_facts_round_trip_and_forbid_extra():
    f = VisionFacts(
        image_sha256="ab" * 32, scene=SceneType.ACCIDENT, objects=["car"],
        damage_severity=DamageSeverity.HIGH, injuries_visible=True,
        confidence={"scene": 0.9}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.5,
    )
    assert f.status is VisionStatus.OK
    again = VisionFacts.model_validate(f.model_dump(mode="json"))
    assert again == f
    try:
        VisionFacts.model_validate({**f.model_dump(mode="json"), "bogus": 1})
        raise AssertionError("extra field must be rejected")
    except ValueError:
        pass


def test_vision_facts_failed_factory_keeps_required_fields():
    f = VisionFacts.failed(
        image_sha256="cd" * 32, mode=VisionMode.LIVE,
        model_id="qwen", model_version="4bit", latency_ms=0.0,
        status=VisionStatus.UNAVAILABLE, error_code="timeout",
    )
    assert f.status is VisionStatus.UNAVAILABLE
    assert f.error_code == "timeout"
    assert f.scene is SceneType.UNKNOWN
    assert f.damage_severity is DamageSeverity.UNKNOWN


def test_upload_request_bounds_and_forbid():
    UploadRequest(image_b64="aGk=")  # minimal ok
    for bad in ({"image_b64": ""}, {"image_b64": "aGk=", "x": 1}):
        try:
            UploadRequest.model_validate(bad)
            raise AssertionError(f"must reject {bad}")
        except ValueError:
            pass
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/vision/test_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vision'`

- [ ] **Step 3: Implement `vision/schema.py`**

```python
# vision/schema.py
"""Structured facts extracted from an image. Evidence, not authority: nothing in
this module may write severity or enter a model state (spec: vision-evidence)."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

MAX_IMAGE_BYTES = 5_000_000
MAX_B64_CHARS = 7_000_000
MAX_OBJECTS = 16


class VisionStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"


class VisionMode(StrEnum):
    MOCK = "mock"
    CACHE = "cache"
    LIVE = "live"


class SceneType(StrEnum):
    ACCIDENT = "accident"
    FIRE = "fire"
    FLOOD = "flood"
    TRAFFIC = "traffic"
    OTHER = "other"
    UNKNOWN = "unknown"


class DamageSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class VisionFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scene: SceneType = SceneType.UNKNOWN
    objects: list[str] = Field(default_factory=list, max_length=MAX_OBJECTS)
    damage_severity: DamageSeverity = DamageSeverity.UNKNOWN
    injuries_visible: bool | None = None
    confidence: dict[str, float] = Field(default_factory=dict)
    model_id: str
    model_version: str
    mode: VisionMode
    latency_ms: float = Field(ge=0)
    status: VisionStatus = VisionStatus.OK
    error_code: str | None = None

    @classmethod
    def failed(
        cls,
        *,
        image_sha256: str,
        mode: VisionMode,
        model_id: str,
        model_version: str,
        latency_ms: float,
        status: VisionStatus,
        error_code: str,
    ) -> "VisionFacts":
        return cls(
            image_sha256=image_sha256, scene=SceneType.UNKNOWN,
            damage_severity=DamageSeverity.UNKNOWN, injuries_visible=None,
            model_id=model_id, model_version=model_version, mode=mode,
            latency_ms=latency_ms, status=status, error_code=error_code,
        )


class UploadRequest(BaseModel):
    """Shared JSON-base64 upload body (POST /api/images and POST /images)."""

    model_config = ConfigDict(extra="forbid")

    image_b64: str = Field(min_length=1, max_length=MAX_B64_CHARS)
    filename: str | None = Field(default=None, max_length=255)


class UploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    mime: str
    facts: VisionFacts


class FactsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    facts: VisionFacts | None = None
```

Create `vision/__init__.py` (initially schema-only so Task 1 imports work; Tasks 2–4 extend it):

```python
"""Shared vision evidence component (mock | cache | live)."""
from .schema import (
    DamageSeverity, FactsResponse, SceneType, UploadRequest, UploadResponse,
    VisionFacts, VisionMode, VisionStatus,
)

__all__ = [
    "DamageSeverity", "FactsResponse", "SceneType", "UploadRequest",
    "UploadResponse", "VisionFacts", "VisionMode", "VisionStatus",
]
```

Task 2 appends `from .store import ImageStore, sniff_mime` and Task 4 appends
`from .analyzer import VisionAnalyzer` to the imports and `__all__` — do **not**
import `.analyzer`/`.store` in Task 1 (they don't exist yet and every test import
would crash).

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/vision/test_schema.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add vision/ tests/vision/test_schema.py
git commit -m "vision: VisionFacts schema + shared upload contracts"
```

---

### Task 2: `vision/store.py` — content-addressed store + MIME sniff + fixtures

**Files:**
- Create: `vision/store.py`, `fixtures/vision/scene.png`, `fixtures/vision/not-image.txt`
- Test: `tests/vision/test_store.py`

**Interfaces:**
- Produces: `ImageStore(root: Path, max_entries: int = 50)` with `put(data, mime) -> sha256`, `get_bytes(sha) -> bytes | None`, `meta(sha) -> ImageMeta | None`, `set_facts(sha, facts)`, `path(sha) -> Path | None`; `sniff_mime(data) -> str | None`.
- Consumes: `VisionFacts` (Task 1), `MAX_IMAGE_BYTES`.

- [ ] **Step 1: Create fixtures (one-time, committed)**

```bash
mkdir -p fixtures/vision
uv run python - <<'EOF'
import struct, zlib
from pathlib import Path

def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

w = h = 16
raw = b"".join(b"\x00" + bytes([200, 60, 40] * w) for _ in range(h))
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(raw))
       + chunk(b"IEND", b""))
Path("fixtures/vision/scene.png").write_bytes(png)
Path("fixtures/vision/not-image.txt").write_text("this is not an image\n")
print("wrote", len(png), "byte png")
EOF
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/vision/test_store.py
from pathlib import Path

import pytest

from vision.schema import DamageSeverity, SceneType, VisionFacts, VisionMode
from vision.store import ImageStore, sniff_mime

PNG = Path("fixtures/vision/scene.png").read_bytes()
NOT_IMAGE = Path("fixtures/vision/not-image.txt").read_bytes()


def test_sniff_mime():
    assert sniff_mime(PNG) == "image/png"
    assert sniff_mime(NOT_IMAGE) is None
    assert sniff_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff_mime(b"RIFFxxxxWEBP") == "image/webp"


def test_put_is_content_addressed_and_idempotent(tmp_path):
    store = ImageStore(tmp_path)
    sha1 = store.put(PNG, "image/png")
    sha2 = store.put(PNG, "image/png")
    assert sha1 == sha2  # same bytes -> same id
    assert store.get_bytes(sha1) == PNG
    assert (tmp_path / f"{sha1}.png").is_file()


def test_set_and_get_facts(tmp_path):
    store = ImageStore(tmp_path)
    sha = store.put(PNG, "image/png")
    assert store.meta(sha).facts is None
    facts = VisionFacts(
        image_sha256=sha, scene=SceneType.FIRE, objects=["flames"],
        damage_severity=DamageSeverity.HIGH, injuries_visible=None,
        confidence={"scene": 0.8}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.0,
    )
    store.set_facts(sha, facts)
    assert store.meta(sha).facts == facts
    assert store.meta("0" * 64) is None
    assert store.get_bytes("0" * 64) is None


def test_evicts_oldest_beyond_cap(tmp_path):
    store = ImageStore(tmp_path, max_entries=2)
    shas = [store.put(bytes([i]) * 4, "image/png") for i in range(3)]
    assert store.meta(shas[0]) is None  # oldest evicted
    assert not (tmp_path / f"{shas[0]}.png").exists()
    assert store.meta(shas[1]) is not None
    assert store.meta(shas[2]) is not None
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/vision/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError`/`ImportError`

- [ ] **Step 4: Implement**

```python
# vision/store.py
"""Content-addressed image storage: bytes keyed by sha256, metadata registry
capped like jevcity's sandbox_store (oldest evicted). No wall-clock timestamps —
image metadata must never introduce a host-clock time base."""
from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .schema import MAX_IMAGE_BYTES, VisionFacts

_MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"RIFF", "image/webp", "webp"),  # refined below: RIFF....WEBP
)
_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_STORE_ENTRIES = 50


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode_b64(image_b64: str) -> bytes:
    """Strict base64 decode + size cap; raises ValueError with a client-safe message."""
    if len(image_b64) > 7_000_000:
        raise ValueError("image_b64 too large")
    try:
        data = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("image_b64 is not valid base64") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError(f"image exceeds {MAX_IMAGE_BYTES} bytes")
    return data


class ImageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    mime: str
    size_bytes: int
    facts: VisionFacts | None = None


class ImageStore:
    def __init__(self, root: Path, max_entries: int = MAX_STORE_ENTRIES) -> None:
        self.root = Path(root)
        self.max_entries = max_entries
        self._meta: dict[str, ImageMeta] = {}  # insertion order = eviction order

    def put(self, data: bytes, mime: str) -> str:
        sha = hashlib.sha256(data).hexdigest()
        ext = _EXT_BY_MIME[mime]
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{sha}.{ext}"
        if not path.exists():
            path.write_bytes(data)
        if sha in self._meta:
            self._meta.move_to_end(sha) if hasattr(self._meta, "move_to_end") else None
        else:
            self._meta[sha] = ImageMeta(image_id=sha, mime=mime, size_bytes=len(data))
            while len(self._meta) > self.max_entries:
                old_sha, old = self._meta.popitem(last=False)
                old_path = self.root / f"{old_sha}.{_EXT_BY_MIME[old.mime]}"
                old_path.unlink(missing_ok=True)
        return sha

    def meta(self, image_id: str) -> ImageMeta | None:
        return self._meta.get(image_id)

    def set_facts(self, image_id: str, facts: VisionFacts) -> None:
        meta = self._meta.get(image_id)
        if meta is None:
            raise KeyError(image_id)
        meta.facts = facts

    def get_bytes(self, image_id: str) -> bytes | None:
        meta = self._meta.get(image_id)
        if meta is None:
            return None
        path = self.root / f"{image_id}.{_EXT_BY_MIME[meta.mime]}"
        return path.read_bytes() if path.exists() else None

    def path(self, image_id: str) -> Path | None:
        meta = self._meta.get(image_id)
        if meta is None:
            return None
        p = self.root / f"{image_id}.{_EXT_BY_MIME[meta.mime]}"
        return p if p.exists() else None
```

Note: plain `dict` preserves insertion order, so write eviction as a plain `else` branch — `self._meta[sha] = ImageMeta(...)` on insert, then `while len(self._meta) > self.max_entries: old_sha, old = self._meta.popitem(last=False)` unlinking the old file. Drop the `move_to_end`/`hasattr` line from the sketch above.

- [ ] **Step 5: Run to verify pass, then lint + commit**

Run: `uv run pytest tests/vision/test_store.py -v && uv run ruff check .`
Expected: 4 passed, All checks passed

```bash
git add vision/store.py fixtures/vision tests/vision/test_store.py
git commit -m "vision: content-addressed image store with MIME sniffing"
```

---

### Task 3: `vision/analyzer.py` — mock + cache modes

**Files:**
- Create: `vision/analyzer.py`
- Test: `tests/vision/test_analyzer.py`

**Interfaces:**
- Produces: `VisionAnalyzer(mode=VisionMode.MOCK, *, cache=None, live_timeout_s=15.0)` with `analyze(data: bytes, *, image_path: Path | None = None) -> VisionFacts` and `health() -> dict`; module constant `VISION_MODEL_ID`.
- Consumes: Task 1 schema, `sniff_mime` (for a cheap sanity check).

- [ ] **Step 1: Write the failing tests**

```python
# tests/vision/test_analyzer.py
from pathlib import Path

from vision.analyzer import VisionAnalyzer
from vision.schema import VisionMode, VisionStatus

PNG = Path("fixtures/vision/scene.png").read_bytes()


def test_mock_is_deterministic_from_bytes():
    a = VisionAnalyzer(mode=VisionMode.MOCK).analyze(PNG)
    b = VisionAnalyzer(mode=VisionMode.MOCK).analyze(PNG)
    assert a == b
    assert a.status is VisionStatus.OK
    assert a.mode is VisionMode.MOCK
    assert a.image_sha256 == b.image_sha256
    assert a.confidence  # per-field confidences populated
    # different bytes -> (almost surely) different facts
    other = VisionAnalyzer(mode=VisionMode.MOCK).analyze(PNG + b"\x00")
    assert (other.scene, other.damage_severity) != (a.scene, a.damage_severity) or \
           other.image_sha256 != a.image_sha256


def test_cache_populates_on_hit():
    cache: dict = {}
    first = VisionAnalyzer(mode=VisionMode.CACHE, cache=cache).analyze(PNG)
    assert first.image_sha256 in cache
    second = VisionAnalyzer(mode=VisionMode.CACHE, cache=cache).analyze(PNG)
    assert second == first  # served from cache, not recomputed


def test_cache_miss_without_model_is_fail_closed(monkeypatch):
    import vision.analyzer as va
    monkeypatch.setattr(va, "_live_facts", None)  # no model available
    facts = VisionAnalyzer(mode=VisionMode.CACHE, cache={}).analyze(PNG)
    assert facts.status is VisionStatus.UNAVAILABLE
    assert facts.error_code == "cache_miss_and_no_model"


def test_health_reports_mode_and_model():
    h = VisionAnalyzer(mode=VisionMode.MOCK).health()
    assert h["mode"] == "mock"
    assert h["model_id"]
    assert h["live_model_loaded"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/vision/test_analyzer.py -v`
Expected: FAIL — cannot import `vision.analyzer`

- [ ] **Step 3: Implement mock + cache (live is Task 4)**

```python
# vision/analyzer.py
"""VisionAnalyzer — deliberately mirrors LayaAdapter semantics: mock (deterministic
from image bytes), cache (keyed by sha256), live (mlx-vlm, thread-timeout, fail-closed)."""
from __future__ import annotations

import hashlib
import time

from .schema import (
    DamageSeverity, SceneType, VisionFacts, VisionMode, VisionStatus,
)

MOCK_MODEL_ID = "mock-vlm"
MOCK_MODEL_VERSION = "0.1.0"
VISION_MODEL_ID = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
LIVE_TIMEOUT_S = 15.0
LIVE_PROMPT = (
    'Reply ONLY with JSON: {"scene": "accident|fire|flood|traffic|other", '
    '"damage_severity": "low|medium|high", '
    '"injuries_visible": true|false|null, "objects": ["max 8 short words"]}'
)

_SCENES = [SceneType.ACCIDENT, SceneType.FIRE, SceneType.FLOOD,
           SceneType.TRAFFIC, SceneType.OTHER]
_DAMAGE = [DamageSeverity.LOW, DamageSeverity.MEDIUM, DamageSeverity.HIGH]
_OBJECT_POOL = ["car", "truck", "water", "smoke", "flames", "debris",
                "cones", "crowd", "bus", "bike"]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mock_facts(sha: str, mode: VisionMode, latency_ms: float) -> VisionFacts:
    """Pure function of the image digest → byte-identical across restarts."""
    b = bytes.fromhex(sha)
    return VisionFacts(
        image_sha256=sha,
        scene=_SCENES[b[0] % len(_SCENES)],
        objects=[_OBJECT_POOL[b[i] % len(_OBJECT_POOL)] for i in (1, 2, 3) if b[i] % 4],
        damage_severity=_DAMAGE[b[4] % len(_DAMAGE)],
        injuries_visible=None if b[5] % 3 == 0 else bool(b[5] % 2),
        confidence={
            "scene": round(0.50 + (b[6] % 50) / 100, 2),
            "damage_severity": round(0.50 + (b[7] % 50) / 100, 2),
        },
        model_id=MOCK_MODEL_ID,
        model_version=MOCK_MODEL_VERSION,
        mode=mode,
        latency_ms=latency_ms,
    )


class VisionAnalyzer:
    def __init__(
        self,
        mode: VisionMode = VisionMode.MOCK,
        *,
        cache: dict[str, VisionFacts] | None = None,
        live_timeout_s: float = LIVE_TIMEOUT_S,
    ) -> None:
        self.mode = mode
        self.cache: dict[str, VisionFacts] = cache if cache is not None else {}
        self.live_timeout_s = live_timeout_s
        self._live_failures = 0

    def health(self) -> dict[str, str | bool | float]:
        return {
            "mode": self.mode.value,
            "model_id": VISION_MODEL_ID,
            "live_model_loaded": _VLIVE.get("loaded", False),
            "live_timeout_s": self.live_timeout_s,
        }

    def analyze(self, data: bytes, *, image_path=None) -> VisionFacts:
        sha = _sha256(data)
        t0 = time.perf_counter()
        if self.mode is VisionMode.MOCK:
            return _mock_facts(sha, self.mode, round((time.perf_counter() - t0) * 1000, 3))
        if self.mode is VisionMode.CACHE and sha in self.cache:
            return self.cache[sha]
        # cache miss (or live): need the real model
        if _live_facts is None:  # module-level, patched in tests / None w/o mlx-vlm
            return VisionFacts.failed(
                image_sha256=sha, mode=self.mode, model_id=VISION_MODEL_ID,
                model_version="n/a", latency_ms=0.0,
                status=VisionStatus.UNAVAILABLE,
                error_code="cache_miss_and_no_model",
            )
        facts = _run_live(_live_facts, data, image_path, sha, self.mode,
                          self.live_timeout_s)
        if facts.status is VisionStatus.OK and self.mode is VisionMode.CACHE:
            self.cache[sha] = facts
        return facts


# --- live plumbing (Task 4 replaces this stub) -------------------------------
_VLIVE = {"loaded": False}
```

For Task 3 the live path must exist as a **patchable name**: define module-level `_live_facts = None` initially, plus a `_run_live(...)` that raises `AssertionError("live not implemented")` — Task 4 implements both. This keeps Task 3's tests green (they never call live with `_live_facts` set).

- [ ] **Step 4: Run to verify pass, lint, commit**

Run: `uv run pytest tests/vision/test_analyzer.py -v && uv run ruff check .`
Expected: 4 passed, All checks passed

```bash
git add vision/analyzer.py tests/vision/test_analyzer.py
git commit -m "vision: analyzer with deterministic mock and cache modes"
```

---

### Task 4: Live mode (mlx-vlm, optional extra) + model-marked smoke test

**Files:**
- Modify: `vision/analyzer.py` (replace stub), `pyproject.toml` (extra + wheel packages), `.gitignore`
- Test: `tests/vision/test_live.py`

**Interfaces:**
- Produces: `_live_facts(data, image_path, model_id) -> dict`-loader (module-level, patchable); live path in `VisionAnalyzer.analyze`; `uv sync --extra vision` install path.
- Consumes: Task 2's `ImageStore.path` (live needs a real file path).

- [ ] **Step 1: pyproject + gitignore changes**

```toml
# pyproject.toml — add after dependencies:
[project.optional-dependencies]
vision = ["mlx-vlm>=0.4"]

# and extend the wheel target:
[tool.hatch.build.targets.wheel]
packages = ["adip", "jevcity", "vision"]
```

```
# .gitignore — append
datasets/vision/images/
```

Run: `uv sync --frozen` — if the lock rejects the new optional group, run `uv lock` and commit `uv.lock`.

- [ ] **Step 2: Write the failing smoke test**

```python
# tests/vision/test_live.py
"""Live mlx-vlm smoke — model tier: deselected by default (pytest addopts),
run explicitly with: uv run pytest -q -m model tests/vision/test_live.py
Requires: uv sync --extra vision"""
from pathlib import Path

import pytest

from vision.analyzer import VisionAnalyzer
from vision.schema import VisionMode, VisionStatus

PNG = Path("fixtures/vision/scene.png").read_bytes()

pytestmark = pytest.mark.model


def test_live_analyze_returns_facts_or_fail_closed():
    facts = VisionAnalyzer(mode=VisionMode.LIVE).analyze(PNG)
    # Live must never raise: either structured facts or an explicit fail-closed status.
    assert facts.status in (VisionStatus.OK, VisionStatus.UNAVAILABLE,
                            VisionStatus.INVALID_RESPONSE)
    if facts.status is VisionStatus.OK:
        assert facts.scene
        assert facts.model_id
        assert facts.confidence
    else:
        assert facts.error_code


def test_live_malformed_image_fails_closed_not_crash():
    from vision.analyzer import VisionAnalyzer
    facts = VisionAnalyzer(mode=VisionMode.LIVE).analyze(b"definitely-not-an-image")
    assert facts.status is not VisionStatus.OK or facts.scene
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest -q -m model tests/vision/test_live.py`
Expected: FAIL — `_run_live` still raises / `_live_facts is None` → wrong status path (see Task 3 stub).

- [ ] **Step 4: Implement live path**

Replace the stub in `vision/analyzer.py`:

```python
_VLIVE: dict[str, object] = {}  # module cache: {"model":…, "processor":…, "config":…, "loaded": bool}


def _live_facts(data: bytes, image_path, model_id: str) -> dict:
    """Load (once) and call mlx-vlm. Raises on any failure — caller fail-closes."""
    import json as _json
    import re

    from mlx_vlm import generate, load  # optional extra: uv sync --extra vision

    if "model" not in _VLIVE:
        _VLIVE.update(load(model_id))
        _VLIVE["loaded"] = True
    out = generate(
        _VLIVE["model"], _VLIVE["processor"], LIVE_PROMPT,
        image=str(image_path), max_tokens=256,
    )
    m = re.search(r"\{.*\}", str(out), re.DOTALL)
    if not m:
        raise ValueError("no JSON object in model output")
    return _json.loads(m.group(0))


def _run_live(loader, data, image_path, sha, mode, timeout_s) -> VisionFacts:
    if image_path is None:
        return VisionFacts.failed(
            image_sha256=sha, mode=mode, model_id=VISION_MODEL_ID,
            model_version="n/a", latency_ms=0.0,
            status=VisionStatus.UNAVAILABLE, error_code="no_image_path",
        )
    t0 = time.perf_counter()
    box: dict[str, object] = {}
    def worker():
        try:
            box["raw"] = loader(data, image_path, VISION_MODEL_ID)
        except Exception as exc:  # fail-closed: any model error → structured failure
            box["error"] = f"{type(exc).__name__}: {exc}"[:200]
    th = threading.Thread(target=worker, daemon=True)
    th.start()
    th.join(timeout_s)
    latency = round((time.perf_counter() - t0) * 1000, 3)
    if th.is_alive():
        return VisionFacts.failed(
            image_sha256=sha, mode=mode, model_id=VISION_MODEL_ID,
            model_version="4bit", latency_ms=latency,
            status=VisionStatus.UNAVAILABLE, error_code="timeout",
        )
    if "error" in box:
        return VisionFacts.failed(
            image_sha256=sha, mode=mode, model_id=VISION_MODEL_ID,
            model_version="4bit", latency_ms=latency,
            status=VisionStatus.UNAVAILABLE, error_code="live_error",
        )
    try:
        raw = box["raw"]
        scene = SceneType(str(raw.get("scene", "unknown")).lower())
    except ValueError:
        scene = SceneType.UNKNOWN
    try:
        damage = DamageSeverity(str(raw.get("damage_severity", "unknown")).lower())
    except ValueError:
        damage = DamageSeverity.UNKNOWN
    objs = [str(o)[:32] for o in raw.get("objects", []) if isinstance(o, str)][:16] \
        if isinstance(raw, dict) else []
    if not isinstance(raw, dict) or ("scene" not in raw and "damage_severity" not in raw):
        return VisionFacts.failed(
            image_sha256=sha, mode=mode, model_id=VISION_MODEL_ID,
            model_version="4bit", latency_ms=latency,
            status=VisionStatus.INVALID_RESPONSE, error_code="missing_fields",
        )
    inj = raw.get("injuries_visible")
    return VisionFacts(
        image_sha256=sha, scene=scene, objects=objs, damage_severity=damage,
        injuries_visible=inj if isinstance(inj, bool) else None,
        confidence={"scene": 0.0, "damage_severity": 0.0},  # live model is uncalibrated
        model_id=VISION_MODEL_ID, model_version="4bit", mode=mode,
        latency_ms=latency,
    )
```

Add `import threading` at the top. **Verify the mlx-vlm API against the installed version before relying on the signature** (it moves):

```bash
uv sync --extra vision && uv run python -c "import mlx_vlm, inspect; print(inspect.signature(mlx_vlm.generate)); print(inspect.signature(mlx_vlm.load))"
```

If the signature differs, adjust the `load`/`generate` call to match the installed version (record the version pinned in `uv.lock`). The smoke test is the contract: it must pass or fail-closed, never raise.

- [ ] **Step 5: Run both tiers**

Run: `uv run pytest -q -m "not model" && uv run pytest -q -m model tests/vision/test_live.py`
Expected: model-free tier all passed; live smoke PASS (or fail-closed assertions pass on this machine). If mlx-vlm cannot be installed/run here, report it as a **limitation** — do not delete or weaken the test.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore vision/analyzer.py tests/vision/test_live.py
git commit -m "vision: live mlx-vlm mode behind optional extra, fail-closed"
```

---

### Task 5: JevCity schemas — vision API models, `IncidentRecord.vision`, schema export

**Files:**
- Create: `jevcity/schemas/vision_api.py`
- Modify: `jevcity/schemas/resources.py` (add `vision` field), `jevcity/schemas/__init__.py`, `jevcity/schemas/export.py`, `jevcity/ingestion/vision_findings.py`
- Test: `tests/jevcity/test_vision_api.py` (start file here; routes added in Task 7)

**Interfaces:**
- Produces: `VisionAttachment(image_id, facts, soft_findings, latest_decision_id)`, `VisionAttachRequest`, `VisionAttachResponse`, `VisionModeRequest`, `VisionModeResponse`, `vision_findings(facts, incident) -> list[ValidationFinding]`; `IncidentRecord.vision: VisionAttachment | None = None`; export slugs for all new models.
- Consumes: `VisionFacts` (re-exported through `jevcity.schemas`), `IncidentRecord`, `ValidationFinding`, `SeverityHint`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/jevcity/test_vision_api.py  (Task 5 portion)
from jevcity.ingestion.vision_findings import vision_findings
from jevcity.schemas import IncidentRecord, SeverityHint, VisionFacts, VisionMode
from jevcity.schemas import SceneType, DamageSeverity, VisionStatus
from datetime import datetime, timezone


def _incident(severity: SeverityHint) -> IncidentRecord:
    return IncidentRecord(
        incident_id="inc-1", incident_type="accident", zone="north",
        first_seen_simulated=datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc),
        latest_simulated=datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc),
        validation_status="valid",
    )


def _facts(damage: DamageSeverity) -> VisionFacts:
    return VisionFacts(
        image_sha256="ab" * 32, scene=SceneType.ACCIDENT, objects=["car"],
        damage_severity=damage, injuries_visible=True,
        confidence={"scene": 0.9}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.0,
    )


def test_mismatch_raises_soft_flag():
    inc = _incident(SeverityHint.MINOR)
    findings = vision_findings(_facts(DamageSeverity.HIGH), inc)
    assert [f.code for f in findings] == ["severity_mismatch_vision"]
    assert findings[0].severity == "soft"


def test_agreement_or_unknown_raises_nothing():
    for sev, dmg in ((SeverityHint.MODERATE, DamageSeverity.MEDIUM),
                     (SeverityHint.SEVERE, DamageSeverity.HIGH),
                     (SeverityHint.MINOR, DamageSeverity.LOW),
                     (SeverityHint.MINOR, DamageSeverity.UNKNOWN)):
        assert vision_findings(_facts(dmg), _incident(sev)) == []


def test_unavailable_facts_raise_nothing():
    f = _facts(DamageSeverity.HIGH)
    failed = VisionFacts.failed(
        image_sha256=f.image_sha256, mode=VisionMode.LIVE, model_id="qwen",
        model_version="4bit", latency_ms=1.0, status=VisionStatus.UNAVAILABLE,
        error_code="timeout",
    )
    assert vision_findings(failed, _incident(SeverityHint.MINOR)) == []


def test_incident_record_accepts_optional_vision():
    inc = _incident(SeverityHint.MINOR)
    assert inc.vision is None
    inc.vision = None  # additive default; extra=forbid unaffected
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/jevcity/test_vision_api.py -v`
Expected: FAIL — `ImportError: cannot import name 'vision_findings'`

- [ ] **Step 3: Implement**

`jevcity/ingestion/vision_findings.py`:

```python
"""Vision evidence → soft validation findings. Evidence, not authority: this is
the ONLY lever vision has into policy (spec: no severity writes, no ML triad)."""
from __future__ import annotations

from jevcity.schemas import (
    DamageSeverity, IncidentRecord, SceneType, SeverityHint, ValidationFinding,
    VisionFacts, VisionStatus,
)

_RANK = {SeverityHint.MINOR: 0, SeverityHint.MODERATE: 1,
         SeverityHint.SEVERE: 2, SeverityHint.CRITICAL: 3}
_DAMAGE_RANK = {DamageSeverity.LOW: 0, DamageSeverity.MEDIUM: 1,
                DamageSeverity.HIGH: 2}


def vision_findings(facts: VisionFacts, incident: IncidentRecord) -> list[ValidationFinding]:
    if facts.status is not VisionStatus.OK:
        return []
    if incident.severity_hint is None or facts.damage_severity is DamageSeverity.UNKNOWN:
        return []
    gap = _DAMAGE_RANK[facts.damage_severity] - _RANK.get(incident.severity_hint, 1)
    if gap >= 2:
        return [ValidationFinding(
            severity="soft", code="severity_mismatch_vision",
            message=(f"vision damage={facts.damage_severity.value} vs reported "
                     f"severity={incident.severity_hint.value} (evidence only)"),
        )]
    return []
```

**Check first:** `IncidentRecord` (jevcity/schemas/resources.py) does not currently carry the originating severity hint — grep (`grep -n "severity" jevcity/schemas/resources.py`). If the field is absent, read it from `incident.notes`-style storage is wrong; instead add **`severity_hint: SeverityHint | None = None`** to `IncidentRecord` alongside `vision` (additive, default None) and have Task 6's `attach_image` populate nothing — the value already exists at incident creation in `simulation/state.py::_add_report`/`inject_incident` (grep `severity` there and set it where the record is created). If records genuinely never store it, fall back to comparing against the **latest decision's** governed priority (grep `priority` on `DecisionRecord`) and adapt `_RANK` accordingly — decide by reading the code, then keep the chosen rule consistent in tests.

`jevcity/schemas/vision_api.py`:

```python
"""Additive vision request/response contracts (routes beyond the frozen 16)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from vision.schema import VisionFacts

from .validation import ValidationFinding


class VisionAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str
    facts: VisionFacts
    soft_findings: list[ValidationFinding] = []
    latest_decision_id: str | None = None


class VisionAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str


class VisionAttachResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str
    vision: VisionAttachment


class VisionModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str  # validated against VisionMode in the route (mirrors LayaModeRequest)


class VisionModeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_mode: str
    mode: str
```

(Prefer `mode: VisionMode` directly to mirror `LayaModeRequest`; shown as str only if export needs it — use the enum.)

`jevcity/schemas/resources.py` — add to `IncidentRecord`:

```python
    vision: "VisionAttachment | None = Field(
        default=None,
        description=\"Vision evidence attached post-decision (display + soft flags only).\",
    )"
```

(with a proper import; pydantic handles the forward ref since `vision_api` imports from `.resources`' siblings — simplest is importing `VisionAttachment` at the bottom of `vision_api.py` via `IncidentRecord.model_rebuild()` if needed. Use the pattern already present in the codebase for cross-file model refs — grep `model_rebuild` first).

`jevcity/schemas/__init__.py` — re-export: `VisionFacts`, `VisionMode`, `VisionStatus`, `SceneType`, `DamageSeverity` (from vision.schema), plus `VisionAttachment`, `VisionAttachRequest`, `VisionAttachResponse`, `VisionModeRequest`, `VisionModeResponse`.

`jevcity/schemas/export.py` — add to `MODELS`:

```python
    "vision_facts": "VisionFacts",
    "upload_request": "UploadRequest",
    "upload_response": "UploadResponse",
    "facts_response": "FactsResponse",
    "vision_attachment": "VisionAttachment",
    "vision_attach_request": "VisionAttachRequest",
    "vision_attach_response": "VisionAttachResponse",
    "vision_mode_request": "VisionModeRequest",
    "vision_mode_response": "VisionModeResponse",
```

(re-export `UploadRequest`/`UploadResponse`/`FactsResponse` in `jevcity/schemas/__init__.py` too.)

- [ ] **Step 4: Regenerate schema JSON + run tests**

```bash
uv run python -m jevcity.schemas.export
uv run pytest tests/jevcity/test_vision_api.py tests/test_schemas_export.py -v
```
Expected: PASS; `schemas/*.json` updated and staged.

- [ ] **Step 5: Commit**

```bash
git add jevcity/schemas jevcity/ingestion/vision_findings.py schemas/ tests/jevcity/test_vision_api.py
git commit -m "jevcity: vision schemas, IncidentRecord.vision, severity-mismatch soft flag"
```

---

### Task 6: `JevCityEngine.attach_image()` — vision attachment + audit entry

**Files:**
- Modify: `jevcity/decision_engine/engine.py`
- Test: append to `tests/jevcity/test_vision_api.py`

**Interfaces:**
- Produces: `JevCityEngine.attach_image(incident_id: str, facts: VisionFacts) -> VisionAttachment` (raises `KeyError` for unknown incident) — consumed by the API route (Task 7).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/jevcity/test_vision_api.py
from jevcity.api.app import build_engine
from jevcity.schemas import DamageSeverity, SceneType, VisionMode


def test_attach_image_sets_incident_and_writes_audit_on_sim_clock():
    engine = build_engine()
    engine.simulation.start(42, 7)
    engine.simulation.inject_incident(
        __import__("jevcity.schemas", fromlist=["IncidentType"]).IncidentType.ACCIDENT,
        __import__("jevcity.schemas", fromlist=["Zone"]).Zone.NORTH,
    )
    records = engine.process_pending()
    incident_id = records[0].incident_id

    facts = VisionFacts(
        image_sha256="ef" * 32, scene=SceneType.ACCIDENT, objects=["car"],
        damage_severity=DamageSeverity.HIGH, injuries_visible=True,
        confidence={"scene": 0.9}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.0,
    )
    att = engine.attach_image(incident_id, facts)
    assert engine.simulation.incidents[incident_id].vision is att
    assert att.latest_decision_id == records[0].decision_id

    entries = [e for e in engine.audit.entries(limit=200)
               if e.action == "VISION_ATTACHED"]
    assert len(entries) == 1
    assert entries[0].incident_id == incident_id
    assert entries[0].timestamp.tzinfo is not None  # sim clock, not naive host time
    # chain still valid after the new entry
    assert engine.audit.validate_chain()


def test_attach_unknown_incident_raises_key_error():
    engine = build_engine()
    facts = VisionFacts(
        image_sha256="ef" * 32, scene=SceneType.OTHER, objects=[],
        damage_severity=DamageSeverity.LOW, injuries_visible=None,
        confidence={}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.0,
    )
    try:
        engine.attach_image("inc-does-not-exist", facts)
        raise AssertionError("expected KeyError")
    except KeyError:
        pass
```

(Clean up the `__import__` hacks — put `IncidentType`, `Zone`, `VisionFacts` in the file's top-level imports.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/jevcity/test_vision_api.py -v -k attach`
Expected: FAIL — `AttributeError: 'JevCityEngine' object has no attribute 'attach_image'`

- [ ] **Step 3: Implement on the engine**

Add next to `apply_override` (mirror its `self.audit.append(...)` kwargs exactly — check `AuditLog.append`'s signature in `jevcity/audit/log.py` while you're there):

```python
    def attach_image(self, incident_id: str, facts: "VisionFacts") -> "VisionAttachment":
        """Attach vision evidence to an incident. Evidence, not authority: records +
        soft flags + audit only — never writes severity (spec: vision-evidence)."""
        from jevcity.ingestion.vision_findings import vision_findings
        incident = self.simulation.incidents.get(incident_id)
        if incident is None:
            raise KeyError(incident_id)
        findings = vision_findings(facts, incident)
        latest = next(
            (d for d in reversed(self.decision_history)
             if d.incident_id == incident_id), None,
        )
        attachment = VisionAttachment(
            image_id=facts.image_sha256, facts=facts, soft_findings=findings,
            latest_decision_id=latest.decision_id if latest else None,
        )
        incident.vision = attachment
        self.audit.append(
            actor="system",
            action="VISION_ATTACHED",
            reason=(f"scene={facts.scene.value}; damage={facts.damage_severity.value}; "
                    f"status={facts.status.value}; findings={[f.code for f in findings]}"),
            before_state="",
            after_state="vision_attached",
            incident_id=incident_id,
            decision_id=attachment.latest_decision_id or "",
            timestamp=self.simulation.clock.now,
        )
        return attachment
```

Import `VisionAttachment`/`VisionFacts` at the top of `engine.py` (they're re-exported by `jevcity.schemas`).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/jevcity/test_vision_api.py -v && uv run ruff check .`
Expected: all passed (adjust the audit-kwargs if `AuditLog.append` names differ — read it, don't guess)

- [ ] **Step 5: Commit**

```bash
git add jevcity/decision_engine/engine.py tests/jevcity/test_vision_api.py
git commit -m "jevcity: attach_image records vision evidence with sim-clock audit entry"
```

---

### Task 7: 4 additive JevCity routes + route-ledger update

**Files:**
- Modify: `jevcity/api/app.py`, `tests/jevcity/test_audit_phase4.py` (`FROZEN_ROUTES`)
- Test: append to `tests/jevcity/test_vision_api.py`

**Interfaces:**
- Produces: `POST /api/images`, `GET /api/images/{image_id}/facts`, `POST /api/incidents/{incident_id}/images`, `POST /api/vision/mode`.
- Consumes: `ImageStore`, `VisionAnalyzer` (app-owned), `engine.attach_image` (Task 6), schemas (Task 5).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/jevcity/test_vision_api.py
import base64
from pathlib import Path

from fastapi.testclient import TestClient

from jevcity.api.app import create_app
from jevcity.schemas import VisionMode

PNG_B64 = base64.b64encode(Path("fixtures/vision/scene.png").read_bytes()).decode()


def _started_client():
    engine = build_engine()
    client = TestClient(create_app(engine))
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    return engine, client


def test_upload_extract_and_facts_get():
    _, client = _started_client()
    r = client.post("/api/images", json={"image_b64": PNG_B64})
    assert r.status_code == 200
    body = r.json()
    assert len(body["image_id"]) == 64
    assert body["mime"] == "image/png"
    assert body["facts"]["status"] == "ok"

    r2 = client.get(f"/api/images/{body['image_id']}/facts")
    assert r2.status_code == 200
    assert r2.json()["facts"]["image_sha256"] == body["image_id"]


def test_upload_422_battery():
    _, client = _started_client()
    bad = [
        {"image_b64": ""},                                        # empty (422 pydantic)
        {"image_b64": base64.b64encode(b"not an image").decode()}, # bad magic
        {"image_b64": "!!!not-base64!!!"},                        # bad encoding
        {"image_b64": PNG_B64, "extra": 1},                       # extra=forbid
    ]
    for payload in bad:
        r = client.post("/api/images", json=payload)
        assert r.status_code == 422, payload


def test_attach_to_incident_and_404s():
    _, client = _started_client()
    img = client.post("/api/images", json={"image_b64": PNG_B64}).json()
    inc = client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "minor"},
    ).json()
    incident_id = inc["incident_ids"][0] if "incident_ids" in inc else None
    if incident_id is None:  # response shape guard — read SimulationActionResponse
        incident_id = client.get("/api/incidents").json()["incidents"][0]["incident_id"]

    r = client.post(f"/api/incidents/{incident_id}/images",
                    json={"image_id": img["image_id"]})
    assert r.status_code == 200
    assert r.json()["vision"]["facts"]["scene"]
    got = client.get(f"/api/incidents/{incident_id}").json()
    assert got["incident"]["vision"]["image_id"] == img["image_id"]

    # 404s
    assert client.get("/api/images/" + "0" * 64 + "/facts").status_code == 404
    assert client.post("/api/incidents/inc-nope/images",
                       json={"image_id": img["image_id"]}).status_code == 404
    assert client.post(f"/api/incidents/{incident_id}/images",
                       json={"image_id": "0" * 64}).status_code == 404


def test_vision_mode_switch_mirrors_laya_mode():
    _, client = _started_client()
    r = client.post("/api/vision/mode", json={"mode": "cache"})
    assert r.status_code == 200
    assert r.json() == {"previous_mode": "mock", "mode": "cache"}
    assert client.post("/api/vision/mode", json={"mode": "quantum"}).status_code == 422
    assert client.post("/api/vision/mode",
                       json={"mode": "live", "extra": 1}).status_code == 422
```

**Note:** the incident-id field name in `SimulationActionResponse` must be read from
the code first — grep `decision_ids` / `incident_ids` in `jevcity/schemas/api.py` and
use the real name in the `test_attach_to_incident_and_404s` setup.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/jevcity/test_vision_api.py -v -k "upload or attach or mode"`
Expected: FAIL — 404 (routes don't exist yet)

- [ ] **Step 3: Implement the routes**

In `jevcity/api/app.py` `create_app()` (after the what-if routes), add:

```python
    from vision.analyzer import VisionAnalyzer
    from vision.store import ImageStore, decode_b64, sniff_mime

    vision_analyzer = VisionAnalyzer(mode=VisionMode.MOCK)
    image_store = ImageStore(Path("datasets/vision/images"))
```

(import at module top with the others; `Path` is already imported.)

```python
    @app.post("/api/images", response_model=ImageUploadResponse)
    def upload_image(req: ImageUploadRequest) -> ImageUploadResponse:
        try:
            data = decode_b64(req.image_b64)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        mime = sniff_mime(data)
        if mime is None:
            raise HTTPException(status_code=422,
                                detail="unrecognized image format (PNG/JPEG/WebP only)")
        image_id = image_store.put(data, mime)
        facts = vision_analyzer.analyze(data, image_path=image_store.path(image_id))
        image_store.set_facts(image_id, facts)
        return ImageUploadResponse(image_id=image_id, mime=mime, facts=facts)

    @app.get("/api/images/{image_id}/facts", response_model=ImageFactsResponse)
    def get_image_facts(image_id: str) -> ImageFactsResponse:
        meta = image_store.meta(image_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="image_id not found")
        return ImageFactsResponse(image_id=image_id, facts=meta.facts)

    @app.post("/api/incidents/{incident_id}/images",
              response_model=VisionAttachResponse)
    def attach_image_to_incident(incident_id: str, req: VisionAttachRequest
                                 ) -> VisionAttachResponse:
        meta = image_store.meta(req.image_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="image_id not found")
        facts = meta.facts or vision_analyzer.analyze(
            image_store.get_bytes(req.image_id) or b"",
            image_path=image_store.path(req.image_id),
        )
        try:
            attachment = engine.attach_image(incident_id, facts)
        except KeyError:
            raise HTTPException(status_code=404, detail="incident_id not found")
        return VisionAttachResponse(incident_id=incident_id, vision=attachment)

    @app.post("/api/vision/mode", response_model=VisionModeResponse)
    def vision_mode_switch(req: VisionModeRequest) -> VisionModeResponse:
        previous = vision_analyzer.mode
        vision_analyzer.mode = req.mode
        return VisionModeResponse(previous_mode=previous.value, mode=req.mode.value)
```

(Use `UploadRequest`/`UploadResponse`/`FactsResponse` from `vision.schema` aliased in the `jevcity.schemas` re-exports — the names `ImageUploadResponse` etc. should be imported consistently; pick one naming scheme across Task 5 exports and Task 7 imports.)

- [ ] **Step 4: Extend the route ledger**

In `tests/jevcity/test_audit_phase4.py`, add to `FROZEN_ROUTES`:

```python
    ("POST", "/api/images"),
    ("GET", "/api/images/{image_id}/facts"),
    ("POST", "/api/incidents/{incident_id}/images"),
    ("POST", "/api/vision/mode"),
```

- [ ] **Step 5: Find any other route-count assertions and update them**

```bash
grep -rn "== 22\|22 routes\|len(routes)\|route_count" tests/ --include="*.py"
```
Update any hits to 26 (this is a count correction, not a weakened assertion — the sets/counts must still be exact).

- [ ] **Step 6: Run the full model-free suite**

Run: `uv run ruff check . && uv run pytest -q -m "not model"`
Expected: all passed (record the new total — README update comes in Task 10)

- [ ] **Step 7: Commit**

```bash
git add jevcity/api/app.py tests/jevcity/ tests/jevcity/test_audit_phase4.py
git commit -m "jevcity: additive vision routes (upload/facts/attach/mode), ledger at 26"
```

---

### Task 8: Dashboard — types, api client, Vision evidence card + upload

**Files:**
- Modify: `dashboard/src/types/api.ts`, `dashboard/src/services/api.ts`, `dashboard/src/components/IncidentInspector.tsx`
- Create: `dashboard/src/components/VisionEvidence.tsx`

**Interfaces:**
- Consumes: `POST /api/images`, `POST /api/incidents/{id}/images`, `IncidentRecord.vision` (Task 7).
- Produces: `<VisionEvidence incident={incident} vision={incident.vision} onUploaded={...} />` rendered by `IncidentInspector`.

- [ ] **Step 1: Add types (`dashboard/src/types/api.ts`)**

```ts
export type VisionStatus = 'ok' | 'unavailable' | 'invalid_response';
export type SceneType = 'accident' | 'fire' | 'flood' | 'traffic' | 'other' | 'unknown';
export type DamageSeverity = 'low' | 'medium' | 'high' | 'unknown';

export interface VisionFacts {
  image_sha256: string;
  scene: SceneType;
  objects: string[];
  damage_severity: DamageSeverity;
  injuries_visible: boolean | null;
  confidence: Record<string, number>;
  model_id: string;
  model_version: string;
  mode: 'mock' | 'cache' | 'live';
  latency_ms: number;
  status: VisionStatus;
  error_code?: string | null;
}

export interface ValidationFinding { severity: string; code: string; message: string; }

export interface VisionAttachment {
  image_id: string;
  facts: VisionFacts;
  soft_findings: ValidationFinding[];
  latest_decision_id?: string | null;
}

export interface UploadResponse { image_id: string; mime: string; facts: VisionFacts; }
export interface VisionAttachResponse { incident_id: string; vision: VisionAttachment; }
```

Add `vision?: VisionAttachment | null;` to the existing `IncidentRecord` interface in the same file.

- [ ] **Step 2: Add client methods (`dashboard/src/services/api.ts`)** — follow the existing `fetchJson` helper:

```ts
  uploadImage: (imageB64: string, filename?: string) =>
    fetchJson<UploadResponse>(`${API_BASE}/images`, {
      method: 'POST',
      body: JSON.stringify({ image_b64: imageB64, filename }),
    }),
  attachImage: (incidentId: string, imageId: string) =>
    fetchJson<VisionAttachResponse>(`${API_BASE}/incidents/${incidentId}/images`, {
      method: 'POST',
      body: JSON.stringify({ image_id: imageId }),
    }),
```

(`API_BASE` is whatever the file already defines — reuse it.)

- [ ] **Step 3: Create `VisionEvidence.tsx`**

```tsx
import { useState } from 'react';
import { api } from '../services/api';
import type { VisionAttachment } from '../types/api';

interface Props {
  incidentId: string;
  vision?: VisionAttachment | null;
}

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export const VisionEvidence: React.FC<Props> = ({ incidentId, vision }) => {
  const [isUploading, setIsUploading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setErrorMsg(null);
    try {
      const b64 = await toBase64(file);
      const up = await api.uploadImage(b64, file.name);
      await api.attachImage(incidentId, up.image_id);
      window.location.reload();  // see note
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="mt-3 border border-slate-700 rounded p-3">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold tracking-wider text-slate-400">
          VISION EVIDENCE
        </h4>
        <label className="cursor-pointer text-xs text-sky-400 hover:text-sky-300">
          {isUploading ? 'Analyzing…' : 'Upload image'}
          <input type="file" accept="image/png,image/jpeg,image/webp"
                 className="hidden" onChange={handleFile} disabled={isUploading} />
        </label>
      </div>
      {errorMsg && <p className="mt-2 text-xs text-red-400">{errorMsg}</p>}
      {vision ? (
        <div className="mt-2 space-y-1 text-xs text-slate-300">
          <p>
            scene <span className="text-slate-100">{vision.facts.scene}</span> · damage{' '}
            <span className="text-slate-100">{vision.facts.damage_severity}</span> ·
            confidence {vision.facts.confidence['scene'] ?? '—'}
          </p>
          <p className="text-slate-500">
            {vision.facts.model_id} @ {vision.facts.mode} ·{' '}
            {vision.facts.status === 'ok' ? 'OK' : vision.facts.status}
          </p>
          {vision.soft_findings.map((f) => (
            <p key={f.code} className="text-amber-400">⚠ {f.message}</p>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">No image attached.</p>
      )}
    </div>
  );
};
```

**Note:** replace `window.location.reload()` with the hook's existing refresh if `useDashboardData` exposes one (grep `fetchAll` in `dashboard/src/hooks/useDashboardData.ts`); prefer that — the dashboard already polls at 1.5 s, so after `attachImage` succeeds you can simply let the next poll pick it up and drop the reload entirely.

Render it in `IncidentInspector.tsx` alongside the existing sections:

```tsx
<VisionEvidence incidentId={incident.id} vision={incident.vision} />
```

(check the actual prop name the inspector receives for the incident — `incident.incident_id` per the API shape.)

- [ ] **Step 4: Build + lint**

Run: `cd dashboard && pnpm build && npx oxlint`
Expected: build succeeds, 0 warnings / 0 errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src
git commit -m "dashboard: vision evidence upload control + facts card"
```

---

### Task 9: ADIP — `POST /images` + `/decide.image_ids` + audit evidence

**Files:**
- Modify: `serving/app.py`, `serving/pipeline.py`
- Test: `tests/test_vision_adip.py`

**Interfaces:**
- Produces: `POST /images` (same `UploadRequest`/`UploadResponse` shape); `DecideRequest.image_ids: list[str]`; `DecisionService.decide(text, vision_facts=[])` returns `explanation` suffixed + `vision` list; audit row gains `vision_json` column (default NULL).
- Consumes: `vision` package (`ImageStore`, `VisionAnalyzer`, schemas).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vision_adip.py
import base64
from pathlib import Path

from fastapi.testclient import TestClient

from serving.app import app

PNG_B64 = base64.b64encode(Path("fixtures/vision/scene.png").read_bytes()).decode()


def test_upload_and_decide_with_evidence(tmp_path, monkeypatch):
    import serving.app as sa
    from vision.store import ImageStore
    monkeypatch.setattr(sa, "_image_store", lambda: ImageStore(tmp_path))
    client = TestClient(app)

    up = client.post("/images", json={"image_b64": PNG_B64})
    assert up.status_code == 200
    image_id = up.json()["image_id"]

    r = client.post("/decide", json={
        "text": "customer cannot log in after password reset",
        "image_ids": [image_id],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["vision"]  # evidence echoed
    assert "[vision:" in body["explanation"]  # rides in the explanation
    # routing gates untouched: same decision without evidence
    plain = client.post("/decide", json={"text": "customer cannot log in after password reset"})
    assert plain.json()["decision"] == body["decision"]


def test_decide_unknown_image_id_is_422():
    client = TestClient(app)
    r = client.post("/decide", json={"text": "some ticket text here",
                                     "image_ids": ["0" * 64]})
    assert r.status_code == 422


def test_decide_without_image_ids_contract_unchanged():
    client = TestClient(app)
    r = client.post("/decide", json={"text": "refund request for order 123"})
    assert r.status_code == 200
    assert r.json()["vision"] == []


def test_upload_bad_image_422():
    client = TestClient(app)
    assert client.post("/images", json={"image_b64": ""}).status_code == 422
    assert client.post("/images",
                       json={"image_b64": base64.b64encode(b"nope").decode()}
                       ).status_code == 422
```

**Careful:** `/decide` writes to the real `serving/audit.db` in tests — check how existing serving tests isolate it (grep `serving/audit` or `AUDIT_DB` in `tests/`); follow that pattern (monkeypatch `sa.AUDIT_DB` / `sa.svc` the same way) so tests never mutate a dev audit file.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_vision_adip.py -v`
Expected: FAIL — 404 on `/images` (route missing)

- [ ] **Step 3: Implement**

`serving/app.py`:

```python
from vision.analyzer import VisionAnalyzer
from vision.schema import FactsResponse, UploadRequest, UploadResponse
from vision.store import ImageStore, decode_b64, sniff_mime

_vision = VisionAnalyzer()
_STORE_ROOT = Path("datasets/vision/images")

def _image_store() -> ImageStore:
    return ImageStore(_STORE_ROOT)  # thin wrapper so tests can monkeypatch


@app.post("/images", response_model=UploadResponse)
def upload_image(req: UploadRequest) -> UploadResponse:
    try:
        data = decode_b64(req.image_b64)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    mime = sniff_mime(data)
    if mime is None:
        raise HTTPException(status_code=422,
                            detail="unrecognized image format (PNG/JPEG/WebP only)")
    store = _image_store()
    image_id = store.put(data, mime)
    facts = _vision.analyze(data, image_path=store.path(image_id))
    store.set_facts(image_id, facts)
    return UploadResponse(image_id=image_id, mime=mime, facts=facts)
```

`DecideRequest` gains:

```python
class DecideRequest(BaseModel):
    text: str = Field(min_length=5, max_length=8000)
    image_ids: list[str] = Field(default_factory=list, max_length=8)
```

`decide` route: resolve evidence before calling the service:

```python
    store = _image_store()
    vision_facts = []
    for iid in req.image_ids:
        meta = store.meta(iid)
        if meta is None or meta.facts is None:
            raise HTTPException(status_code=422,
                                detail=f"unknown image_id: {iid}")
        vision_facts.append(meta.facts)
    out = svc.decide(req.text, vision_facts=vision_facts)
```

`DecideResponse` gains `vision: list[dict] = []`.

`serving/pipeline.py`:

1. `_SCHEMA`: add `vision_json TEXT` to the `CREATE TABLE` column list.
2. In `AuditLog._conn` after `executescript(_SCHEMA)`, add the explicit idempotent migration (schema check, not a swallowed exception):

```python
        cols = {row[1] for row in conn.execute("PRAGMA table_info(decisions)")}
        if "vision_json" not in cols:
            conn.execute("ALTER TABLE decisions ADD COLUMN vision_json TEXT")
```

3. `append`: add the column to the INSERT column list and `record.get("vision_json")` to the values.
4. `DecisionService.decide`:

```python
    def decide(self, text: str, vision_facts: list | None = None) -> dict:
        vision_facts = vision_facts or []
        ...  # existing pipeline loop unchanged
        explanation = state["explanation"]["text"]
        if vision_facts:
            evidence = "; ".join(
                f"{f.scene.value}/{f.damage_severity.value} ({f.status.value})"
                for f in vision_facts
            )
            explanation = f"{explanation}\n[vision: {evidence}]"
        record = { ..., "vision_json": json.dumps(
            [f.model_dump(mode="json") for f in vision_facts]) or None }
        ...
        return { ..., "explanation": explanation,
                 "vision": [f.model_dump(mode="json") for f in vision_facts] }
```

(`vision_json` = `"[]"` when empty is fine — keep `record.get` so `_record_error`'s hand-built dict still inserts.)

5. **Replay must stay bit-for-bit:** `replay()` compares only `state["decision"]` vs stored `decision_json`, and vision never touches `state["decision"]` — add a regression test:

```python
# append to tests/test_vision_adip.py
def test_replay_still_matches_with_vision_evidence():
    # arrange: decide with evidence (as in test 1), then replay
    ... # reuse the upload + decide flow from test_upload_and_decide_with_evidence
    from serving.pipeline import replay
    result = replay(body["decision_id"])
    assert result["matches"] is True
```

- [ ] **Step 4: Run to verify pass + full suite**

Run: `uv run ruff check . && uv run pytest -q -m "not model"`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add serving/ tests/test_vision_adip.py
git commit -m "adip: image upload + decide evidence (vision_json audit column, replay-safe)"
```

---

### Task 10: Docs, full verification, landing

**Files:**
- Modify: `README.md`, `docs/jevcity/API.md`, `docs/jevcity/ARCHITECTURE.md` (+ `GUARDRAIL.md` if its codes list matches the grep)

- [ ] **Step 1: Get the real numbers**

```bash
uv run ruff check . && uv run pytest -q -m "not model" | tail -2
grep -rn "app\.(get\|post)\|@app\." jevcity/api/app.py | wc -l   # route count sanity: expect 26
```

- [ ] **Step 2: `docs/jevcity/API.md`**

- Update "22 routes total (16 frozen + 6 additive)" → "26 routes total (16 frozen + 10 additive)".
- Add the 4 vision routes to the endpoint table with their request/response bodies (from Task 7's signatures).
- Update the `POST /api/images` base64/MIME/size rules in prose (PNG/JPEG/WebP, ≤ 5 MB).

- [ ] **Step 3: `docs/jevcity/ARCHITECTURE.md`**

- New section **Vision evidence (image input)** after "Enhancements E1–E4 + demo-liveness": shared `vision/` package, `mock|cache|live` mirroring the Laya adapter, evidence-not-authority rule (soft flag `severity_mismatch_vision` only; no severity writes; Invariant 16 untouched), content-addressed store + 50-entry cap, `VISION_ATTACHED` sim-clock audit entry, route count 26.
- Tests-map table: add rows for `tests/vision/test_schema.py`, `test_store.py`, `test_analyzer.py`, `test_live.py` (`model` tier), `tests/jevcity/test_vision_api.py`, `tests/test_vision_adip.py`.

- [ ] **Step 4: `README.md` counts (three places, per repo convention)**

- CI line, `Build & run` pytest line, `Docs` → `tests/` bullet: replace **307** with the Task-10 measured model-free total; keep the `pytest -m model` note (now N+2 tests).
- JevCity bullet: "22 endpoints (16 frozen + 6 additive)" → "26 endpoints …", mention vision evidence upload in the enhancements list.
- API/`Build & run` section: add `uv sync --extra vision` (optional live mode) next to `uv sync --frozen`.

- [ ] **Step 5: GUARDRAIL.md conditional**

```bash
grep -n "free_text_notes_present\|missing_injury_count" docs/jevcity/GUARDRAIL.md
```
If (and only if) GUARDRAIL.md lists validation finding codes, add a matching row for `severity_mismatch_vision` (soft, evidence-only). If it doesn't, skip — ARCHITECTURE.md's new section already documents it.

- [ ] **Step 6: Full verification**

```bash
uv run ruff check .
uv run pytest -q -m "not model"          # expect the new total, exit 0
uv run python -m jevcity.schemas.export && git diff --quiet schemas/ || git add schemas/
uv run pytest -q tests/test_schemas_export.py
cd dashboard && pnpm build && npx oxlint && cd ..
```
All must pass; any failure is fixed before proceeding (never delete/skip a test to pass).

- [ ] **Step 7: Manual end-to-end smoke (the interface a human uses)**

The JevCity API runs on :8200 (already up in this workspace — restart it to load new code: kill + `uvicorn jevcity.api.app:app --port 8200` backgrounded, log to `/tmp/jevcity-api.log`):

```bash
B64=$(base64 -i fixtures/vision/scene.png | tr -d '\n')
curl -s -X POST localhost:8200/api/images -H 'content-type: application/json' \
     -d "{\"image_b64\": \"$B64\"}" | head -c 400
curl -s -X POST localhost:8200/api/simulation/start -H 'content-type: application/json' \
     -d '{"session_seed":42,"scenario_seed":7}'
# inject an incident, attach the returned image_id, fetch the incident and confirm .vision
```
Also open the dashboard dev server (:5173), upload the fixture image on an incident, and confirm the facts card renders (screenshot optional).

- [ ] **Step 8: Land via branch + PR (never push to main)**

```bash
git checkout -b feature/vision-evidence
git push -u origin feature/vision-evidence
gh pr create --title "Vision evidence: image upload -> local VLM facts as auditable evidence" \
             --body "$(cat <<'EOF'
Implements docs/superpowers/specs/2026-10-10-vision-evidence-design.md:
shared vision/ package (mock|cache|live), 4 additive JevCity routes (22->26),
IncidentRecord.vision + VISION_ATTACHED sim-clock audit, soft flag
severity_mismatch_vision, ADIP /images + /decide.image_ids (replay-safe
vision_json column), dashboard upload + facts card.
Checks: ruff, pytest -m "not model" (all green), schema export fresh,
pnpm build + oxlint clean.
EOF
)"
# wait for CI (lint + model-free tests), then:
gh pr merge --rebase --delete-branch
```

---

## Self-Review (plan author)

1. **Spec coverage:** shared vision pkg (T1–3) ✓; live mlx-vlm + optional extra (T4) ✓; JevCity 4 routes + ledger (T7) ✓; IncidentRecord.vision + soft flag + audit (T5–6) ✓; dashboard upload + facts card (T8) ✓; ADIP /images + /decide.image_ids + audit + explanation (T9) ✓; error table → 422/404/fail-closed tests in T7/T9, timeouts in T4 ✓; determinism tests (T3) ✓; model-tier smokes (T4) ✓; fixtures (T2) ✓; out-of-scope respected (no ML changes, no auth, no cloud) ✓; docs + counts + PR (T10) ✓. **Deviation from spec, flagged:** the spec's "ADIP ticket form attachment control" has no existing UI to attach it to (ADIP is API-only: `serving/` has no web form) — v1 delivers ADIP as API-only; revisit only if a ticket UI is built.
2. **Placeholder scan:** two in-code notes deliberately flag facts the implementer must read from the code rather than guess (exact `SimulationActionResponse` incident-id field; `IncidentRecord` severity source — both have explicit grep instructions and fallbacks). No TBD/TODO steps.
3. **Type consistency:** `VisionFacts`/`VisionStatus`/`VisionMode` names identical across tasks; `analyze(data, *, image_path)` signature matches T7/T9 call sites; `attach_image(incident_id, facts) -> VisionAttachment` matches T6→T7; store API (`put/get_bytes/meta/set_facts/path`) matches all call sites.
