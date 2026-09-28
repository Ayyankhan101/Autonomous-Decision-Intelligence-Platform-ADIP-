"""Event envelope (plan §3.1, Phase 1). Frozen contract."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import IncidentType, InjectionMode, SeverityHint, Zone

MAX_NOTES_LEN = 500


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone: Zone
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    road_segment_id: str


class ReportedAttributes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: SeverityHint | None = None
    vehicles_involved: int | None = Field(default=None, ge=0, le=200)
    injuries_reported: int | None = Field(default=None, ge=0, le=1000)
    lanes_blocked: int | None = Field(default=None, ge=0, le=20)
    notes: str | None = Field(default=None, max_length=MAX_NOTES_LEN)


class EventContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weather: str | None = None
    traffic_level: str | None = None
    time_of_day_bucket: str | None = None


class QualityHints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_synthetic: bool = True
    injection_mode: InjectionMode | None = None


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    incident_id: str
    source_id: str
    event_type: str = "incident_report"
    incident_type: IncidentType
    simulated_time: datetime
    ingest_time: datetime
    location: Location
    reported_attributes: ReportedAttributes
    context: EventContext = Field(default_factory=EventContext)
    quality_hints: QualityHints = Field(default_factory=QualityHints)
