"""Laya question schema (plan §3.1.1, Phase 0 item 17): priority (choice), needs_human_review
(noul), recommended_resource_type (choice). No score questions for MVP (Invariant 14)."""
from __future__ import annotations

from jevcity.schemas import QuestionDef

QUESTIONS_VERSION = "q-0.1.0"

QUESTIONS: dict[str, QuestionDef] = {
    "priority": QuestionDef(
        type="choice",
        instructions="What operational priority should this incident receive?",
        criteria={
            "LOW": "routine",
            "MEDIUM": "needs attention",
            "HIGH": "significant risk",
            "CRITICAL": "immediate life-safety or major city impact",
        },
    ),
    "needs_human_review": QuestionDef(
        type="noul",
        instructions="Should this incident be held for human review before automation acts?",
        criteria={
            "true": "yes, a human operator must review",
            "false": "no, automated handling ok",
        },
        labels={"true": "A", "false": "B"},
    ),
    "recommended_resource_type": QuestionDef(
        type="choice",
        instructions="What primary resource type is most appropriate?",
        criteria={
            "ambulance": "medical response required",
            "fire_truck": "fire or rescue required",
            "police_unit": "traffic control or security required",
            "flood_response_unit": "flooding response required",
            "traffic_management_unit": "congestion management required",
        },
    ),
}
