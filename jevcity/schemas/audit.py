"""Append-only audit entry (plan §3.1.4). Entries never update or delete (Invariant 8)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import LayaStatus, Priority


class AuditLayaMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    laya_checkpoint: str | None = None
    laya_router_model: str | None = None
    laya_status: LayaStatus | None = None
    laya_state_hash: str | None = None
    laya_questions_hash: str | None = None
    laya_suggested_priority: Priority | None = None
    laya_answer_confidence_priority: float | None = Field(default=None, ge=0, le=1)
    laya_latency_ms: float | None = Field(default=None, ge=0)
    laya_guardrail_applied: bool | None = None


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    timestamp: datetime
    actor: str = Field(min_length=1, description="operator_id or 'system'")
    action: str = Field(min_length=1)
    reason: str = Field(default="", max_length=2000)
    before_state: str | None = None
    after_state: str | None = None
    decision_id: str | None = None
    incident_id: str | None = None
    policy_version: str | None = None
    model_versions: dict[str, str] = Field(default_factory=dict)
    dry_run: bool = False
    laya: AuditLayaMetadata = Field(default_factory=AuditLayaMetadata)
    previous_hash: str = Field(min_length=1)
    entry_hash: str = Field(min_length=1)
