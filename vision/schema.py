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
