"""Additive vision request/response contracts (routes beyond the frozen 16)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from vision.schema import VisionFacts, VisionMode

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

    mode: VisionMode


class VisionModeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    previous_mode: VisionMode
    mode: VisionMode
