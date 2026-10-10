"""VisionAnalyzer — deliberately mirrors LayaAdapter semantics: mock (deterministic
from image bytes), cache (keyed by sha256), live (mlx-vlm, thread-timeout, fail-closed)."""
from __future__ import annotations

import hashlib
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
        if _live_facts is None:
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


# --- live plumbing (Task 4 implements; stub keeps Task 3 fail-closed) --------
_VLIVE: dict[str, object] = {}
_live_facts = None  # becomes the mlx-vlm loader in Task 4


def _run_live(loader, data, image_path, sha, mode, timeout_s) -> VisionFacts:
    raise AssertionError("live path not implemented (Task 4)")
