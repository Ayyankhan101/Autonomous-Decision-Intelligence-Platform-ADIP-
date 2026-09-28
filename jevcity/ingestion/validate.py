"""Validation point 1 (plan §3): input validation before feature engineering.
Hard invalid input cannot produce an automated priority (Invariant 1)."""
from __future__ import annotations

from pydantic import ValidationError

from jevcity.schemas import (
    EventEnvelope,
    ValidationFinding,
    ValidationResult,
    ValidationStatus,
)

_SOFT_CAP = 1.0


def validate_raw(raw: dict) -> ValidationResult:
    event_id = str(raw.get("event_id", "unknown"))
    incident_id = str(raw.get("incident_id", "unknown"))
    try:
        event = EventEnvelope.model_validate(raw)
    except ValidationError as exc:
        findings = [
            ValidationFinding(
                severity="hard",
                code=".".join(str(p) for p in err["loc"]) or "event",
                message=err["msg"],
            )
            for err in exc.errors()
        ]
        return ValidationResult(
            event_id=event_id,
            incident_id=incident_id,
            validation_status=ValidationStatus.HARD_REJECTED,
            hard_errors=findings,
            data_quality_score=_SOFT_CAP,
        )

    warnings: list[ValidationFinding] = []
    attrs = event.reported_attributes
    if attrs.severity and attrs.severity == "severe" and (attrs.injuries_reported or 0) == 0:
        warnings.append(
            ValidationFinding(
                severity="soft", code="missing_injury_count",
                message="severe report with zero/absent injury count",
            )
        )
    if attrs.notes:
        warnings.append(
            ValidationFinding(
                severity="soft", code="free_text_notes_present",
                message="untrusted free-text notes attached (Invariant 16)",
            )
        )
    if event.quality_hints.injection_mode:
        warnings.append(
            ValidationFinding(
                severity="soft", code="injected_data",
                message=f"injection_mode={event.quality_hints.injection_mode}",
            )
        )
    status = ValidationStatus.SOFT_FLAGGED if warnings else ValidationStatus.VALID
    return ValidationResult(
        event_id=event.event_id,
        incident_id=event.incident_id,
        validation_status=status,
        soft_warnings=warnings,
        data_quality_score=min(_SOFT_CAP, 0.1 * len(warnings)),
    )
