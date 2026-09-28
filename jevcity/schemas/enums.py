"""Frozen wire enums for JevCity (plan Rev 2 §3.1–§5.7). Values are lowercase wire strings."""
from __future__ import annotations

from enum import StrEnum


class IncidentType(StrEnum):
    ACCIDENT = "accident"
    FIRE = "fire"
    FLOOD = "flood"
    TRAFFIC_SPIKE = "traffic_spike"


class Zone(StrEnum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    CENTRAL = "central"


class SeverityHint(StrEnum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DecisionState(StrEnum):
    AUTO_APPROVED = "AUTO_APPROVED"
    HOLD_FOR_HUMAN = "HOLD_FOR_HUMAN"
    REJECTED_INPUT = "REJECTED_INPUT"
    CONTENTION_ESCALATION = "CONTENTION_ESCALATION"
    OVERRIDE_ACTIVE = "OVERRIDE_ACTIVE"
    MODEL_DEGRADED = "MODEL_DEGRADED"


class ModelStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    INVALID_INPUT = "invalid_input"


class LayaStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    UNAVAILABLE = "unavailable"


class DecisionSource(StrEnum):
    LAYA_PROPOSED = "laya_proposed"
    POLICY_FINALIZED = "policy_finalized"
    FALLBACK_RULE = "fallback_rule"
    HUMAN_REQUIRED = "human_required"


class ResourceType(StrEnum):
    AMBULANCE = "ambulance"
    FIRE_TRUCK = "fire_truck"
    POLICE_UNIT = "police_unit"
    FLOOD_RESPONSE_UNIT = "flood_response_unit"
    TRAFFIC_MANAGEMENT_UNIT = "traffic_management_unit"


class ResourceStatus(StrEnum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    BUSY = "busy"
    OFFLINE = "offline"


class IncidentLifecycle(StrEnum):
    DETECTED = "detected"
    VALIDATED = "validated"
    PRIORITIZED = "prioritized"
    RESOURCE_ASSIGNED = "resource_assigned"
    ACTIVE = "active"
    RESOLVED = "resolved"


class ValidationStatus(StrEnum):
    VALID = "valid"
    SOFT_FLAGGED = "soft_flagged"
    HARD_REJECTED = "hard_rejected"


class OverrideType(StrEnum):
    CHANGE_PRIORITY = "CHANGE_PRIORITY"
    ASSIGN_RESOURCES = "ASSIGN_RESOURCES"
    DISMISS_INCIDENT = "DISMISS_INCIDENT"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    MARK_DATA_UNTRUSTED = "MARK_DATA_UNTRUSTED"
    OVERRIDE_AUTOMATION_HOLD = "OVERRIDE_AUTOMATION_HOLD"


class InjectionMode(StrEnum):
    MISSING_FIELDS = "missing_fields"
    OUT_OF_RANGE = "out_of_range"
    CONFLICTING_REPORTS = "conflicting_reports"
    ADVERSARIAL_NOTES = "adversarial_notes"


class LayaMode(StrEnum):
    MOCK = "mock"
    CACHE = "cache"
    LIVE = "live"


class LayaReasonCode(StrEnum):
    LAYA_TIMEOUT = "LAYA_TIMEOUT"
    LAYA_INVALID_RESPONSE = "LAYA_INVALID_RESPONSE"
    LAYA_LOW_ANSWER_CONFIDENCE = "LAYA_LOW_ANSWER_CONFIDENCE"
    LAYA_SUGGESTION_BLOCKED_BY_POLICY = "LAYA_SUGGESTION_BLOCKED_BY_POLICY"
    LAYA_FALLBACK_POLICY_ONLY = "LAYA_FALLBACK_POLICY_ONLY"


class WhatIfScenario(StrEnum):
    REMOVE_ONE_AMBULANCE = "remove_one_ambulance"
    CLOSE_ROAD = "close_road"
    SECOND_EMERGENCY = "second_emergency"
