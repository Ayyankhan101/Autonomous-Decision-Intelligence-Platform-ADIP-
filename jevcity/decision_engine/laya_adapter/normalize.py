"""Response normalizer (plan §3.1.2).

ERRATA C2: upstream `answer_confidence` field is unverified for laya-mlx — this layer
DERIVES it (top-of-distribution probability). ERRATA C3: derived values are treated as
UNCALIBRATED until JevCity-fixture temperature fitting exists.
"""
from __future__ import annotations

import hashlib
import json

from jevcity.schemas import (
    ChoiceAnswer,
    LayaRequest,
    LayaStatus,
    NoulAnswer,
    NormalizedLayaResponse,
    Priority,
    ResourceType,
)

CHECKPOINT = "aac6fef/laya-typed-decisions-mlx"
ROUTER_MODEL = "typed-decisions"
DEVICE = "mps"
RUNTIME = "laya-mlx"
PRIORITY_LABELS = [p.value for p in Priority]
RESOURCE_LABELS = [r.value for r in ResourceType]


def hash_questions(request: LayaRequest) -> str:
    payload = json.dumps(
        request.questions, sort_keys=True, separators=(",", ":"), default=str
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def normalize(
    request: LayaRequest,
    raw_answers: dict,
    *,
    state_hash: str,
    questions_hash: str,
    latency_ms: float,
) -> NormalizedLayaResponse:
    """Validate raw answers against the question schema; fail closed (Invariant 12)."""
    normalized: dict[str, ChoiceAnswer | NoulAnswer] = {}
    try:
        priority_raw = raw_answers["priority"]
        choice = str(priority_raw["choice"]).upper()
        if choice not in PRIORITY_LABELS:
            raise ValueError(f"invalid priority choice: {choice}")
        distribution = {k: float(v) for k, v in priority_raw["distribution"].items()}
        top = max(distribution.values())
        normalized["priority"] = ChoiceAnswer(
            choice=choice,
            confidence=float(priority_raw.get("confidence", top)),
            answer_confidence=float(priority_raw.get("answer_confidence", top)),
            distribution=distribution,
        )

        review_raw = raw_answers["needs_human_review"]
        noul = float(review_raw["noul"])
        if not 0.0 <= noul <= 1.0:
            raise ValueError(f"noul out of range: {noul}")
        normalized["needs_human_review"] = NoulAnswer(
            noul=noul,
            answer_confidence=float(review_raw.get("answer_confidence", noul)),
        )

        resource_raw = raw_answers["recommended_resource_type"]
        resource_choice = str(resource_raw["choice"]).lower()
        if resource_choice not in RESOURCE_LABELS:
            raise ValueError(f"invalid resource choice: {resource_choice}")
        distribution = {k: float(v) for k, v in resource_raw.get("distribution", {}).items()}
        top = max(distribution.values()) if distribution else float(
            resource_raw.get("confidence", 0.0)
        )
        normalized["recommended_resource_type"] = ChoiceAnswer(
            choice=resource_choice,
            confidence=float(resource_raw.get("confidence", top)),
            answer_confidence=float(resource_raw.get("answer_confidence", top)),
            distribution=distribution,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return NormalizedLayaResponse.failed(
            LayaStatus.INVALID_RESPONSE,
            runtime=RUNTIME,
            checkpoint=CHECKPOINT,
            router_model=ROUTER_MODEL,
            device=DEVICE,
            state_hash=state_hash,
            questions_hash=questions_hash,
            error_code=f"invalid_output:{exc}",
            latency_ms=latency_ms,
        )

    return NormalizedLayaResponse(
        status=LayaStatus.OK,
        runtime=RUNTIME,
        checkpoint=CHECKPOINT,
        router_model=ROUTER_MODEL,
        device=DEVICE,
        state_hash=state_hash,
        questions_hash=questions_hash,
        answers=normalized,
        latency_ms=latency_ms,
    )
