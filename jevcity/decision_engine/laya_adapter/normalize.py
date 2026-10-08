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


def to_raw(result: dict) -> dict | None:
    """Extract raw-answer payload from a laya_mlx predict result (derived confidences).

    ERRATA C2 verified 2026-09-30 (C1 introspection): upstream answers carry
    choice/probabilities/confidence/noul/action/type but NO answer_confidence —
    derivation here is the contract; upstream `confidence` is intentionally
    unused so eval-measured confidences stay the derived distribution tops.
    """
    answers = result.get("answers") or {}
    try:
        priority = answers["priority"]
        p_dist = {str(k): float(v)
                  for k, v in (priority.get("probabilities") or {}).items()}
        p_choice = str(priority.get("choice") or max(p_dist, key=p_dist.get))
        resource = answers["recommended_resource_type"]
        r_dist = {str(k): float(v)
                  for k, v in (resource.get("probabilities") or {}).items()}
        r_choice = str(resource.get("choice") or max(r_dist, key=r_dist.get))
        noul = float(answers["needs_human_review"]["noul"])
        if not 0.0 <= noul <= 1.0:
            return None
        return {
            "priority": {
                "choice": p_choice,
                "confidence": p_dist.get(p_choice, 0.0),
                "answer_confidence": p_dist.get(p_choice, 0.0),
                "distribution": p_dist,
            },
            "needs_human_review": {
                "noul": noul,
                "answer_confidence": max(noul, 1.0 - noul),
            },
            "recommended_resource_type": {
                "choice": r_choice,
                "confidence": r_dist.get(r_choice, 0.0),
                "answer_confidence": r_dist.get(r_choice, 0.0),
                "distribution": r_dist,
            },
        }
    except (KeyError, TypeError, ValueError):
        return None


def _validate_distribution(
    distribution: dict[str, float], allowed: list[str], label: str
) -> None:
    """Fail closed on malformed distributions (plan §6: negative probability and
    probability-sum errors are errors, unknown option keys exceed the option budget)."""
    unknown = set(distribution) - set(allowed)
    if unknown:
        raise ValueError(f"{label} distribution has unknown options: {sorted(unknown)}")
    for key, value in distribution.items():
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} probability out of range for {key}: {value}")
    total = sum(distribution.values())
    if not 0.99 <= total <= 1.01:
        raise ValueError(f"{label} probability sum out of range: {total}")


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
        _validate_distribution(distribution, PRIORITY_LABELS, "priority")
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
        if distribution:
            _validate_distribution(distribution, RESOURCE_LABELS, "recommended_resource_type")
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
