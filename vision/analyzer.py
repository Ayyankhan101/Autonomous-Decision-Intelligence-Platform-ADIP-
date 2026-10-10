"""VisionAnalyzer — deliberately mirrors LayaAdapter semantics: mock (deterministic
from image bytes), cache (keyed by sha256), live (mlx-vlm, thread-timeout, fail-closed)."""
from __future__ import annotations

import hashlib
import threading
import time

from .schema import (
    DamageSeverity,
    SceneType,
    VisionFacts,
    VisionMode,
    VisionStatus,
)

MOCK_MODEL_ID = "mock-vlm"
MOCK_MODEL_VERSION = "0.1.0"
MOCK_LATENCY_MS = 1.5  # fixed, like LayaAdapter's mock latency — determinism
VISION_MODEL_ID = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
LIVE_TIMEOUT_S = 15.0
LIVE_PROMPT = (
    "Look at the image and answer with EXACTLY ONE JSON object and nothing else "
    "(no prose, no repetition, no markdown). Use only these values — pick the best "
    "fit for what you actually see: "
    '{"scene": "accident|fire|flood|traffic|other", '
    '"damage_severity": "low|medium|high", '
    '"injuries_visible": true or false or null, "objects": [up to 8 short words]}'
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
        latency_ms: float = MOCK_LATENCY_MS,
    ) -> None:
        self.mode = mode
        self.cache: dict[str, VisionFacts] = cache if cache is not None else {}
        self.live_timeout_s = live_timeout_s
        self.latency_ms = latency_ms
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
        if self.mode is VisionMode.MOCK:
            return _mock_facts(sha, self.mode, self.latency_ms)
        if self.mode is VisionMode.CACHE and sha in self.cache:
            return self.cache[sha]
        # cache miss (or live): need the real model
        if _live_facts is None:  # no model loader available (e.g. tests force this)
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


# --- live plumbing (mlx-vlm, optional extra: uv sync --extra vision) --------
_VLIVE: dict[str, object] = {}


def _live_facts(data: bytes, image_path, model_id: str) -> dict:
    """Load (once) and call mlx-vlm. Raises on any failure — caller fail-closes."""
    import json as _json

    from mlx_vlm import generate, load  # optional extra: uv sync --extra vision

    if "model" not in _VLIVE:
        model, processor = load(model_id)  # mlx-vlm 0.7.6: returns (model, processor)
        _VLIVE["model"], _VLIVE["processor"] = model, processor
        _VLIVE["loaded"] = True
    out = generate(
        _VLIVE["model"], _VLIVE["processor"], LIVE_PROMPT,
        image=str(image_path), max_tokens=256,
    )
    text = getattr(out, "text", None) or str(out)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    # first balanced object only — the model may repeat or trail prose
    raw, _ = _json.JSONDecoder().raw_decode(text, start)
    return raw


def _run_live(loader, data, image_path, sha, mode, timeout_s) -> VisionFacts:
    if image_path is None:
        return VisionFacts.failed(
            image_sha256=sha, mode=mode, model_id=VISION_MODEL_ID,
            model_version="n/a", latency_ms=0.0,
            status=VisionStatus.UNAVAILABLE, error_code="no_image_path",
        )
    t0 = time.perf_counter()
    box: dict[str, object] = {}

    def worker() -> None:
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
    raw = box.get("raw")
    if not isinstance(raw, dict) or ("scene" not in raw and "damage_severity" not in raw):
        return VisionFacts.failed(
            image_sha256=sha, mode=mode, model_id=VISION_MODEL_ID,
            model_version="4bit", latency_ms=latency,
            status=VisionStatus.INVALID_RESPONSE, error_code="missing_fields",
        )
    try:
        scene = SceneType(str(raw.get("scene", "unknown")).lower())
    except ValueError:
        scene = SceneType.UNKNOWN
    try:
        damage = DamageSeverity(str(raw.get("damage_severity", "unknown")).lower())
    except ValueError:
        damage = DamageSeverity.UNKNOWN
    objs = [str(o)[:32] for o in raw.get("objects", []) if isinstance(o, str)][:16]
    inj = raw.get("injuries_visible")
    return VisionFacts(
        image_sha256=sha, scene=scene, objects=objs, damage_severity=damage,
        injuries_visible=inj if isinstance(inj, bool) else None,
        confidence={"scene": 0.0, "damage_severity": 0.0},  # live model is uncalibrated
        model_id=VISION_MODEL_ID, model_version="4bit", mode=mode,
        latency_ms=latency,
    )
