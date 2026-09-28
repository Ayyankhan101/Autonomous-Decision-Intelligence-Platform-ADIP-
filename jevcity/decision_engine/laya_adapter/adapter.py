"""Laya adapter (plan §5.4): proposer only — no DB access, no audit writes, no resource
assignment, no invariant overrides. Modes: mock (tests/demo), cache (deterministic replay),
live (Phase 3 — fails closed as unavailable until wired)."""
from __future__ import annotations

import hashlib

from jevcity.schemas import (
    ChoiceAnswer,
    IncidentType,
    LayaMode,
    LayaRequest,
    LayaState,
    LayaStatus,
    NoulAnswer,
    NormalizedLayaResponse,
    Priority,
    ResourceType,
)

from .normalize import CHECKPOINT, DEVICE, ROUTER_MODEL, RUNTIME, hash_questions, normalize
from .questions import QUESTIONS
from .state_builder import hash_state

DTYPE = "float16"

_RESOURCE_BY_TYPE = {
    IncidentType.ACCIDENT: ResourceType.AMBULANCE,
    IncidentType.FIRE: ResourceType.FIRE_TRUCK,
    IncidentType.FLOOD: ResourceType.FLOOD_RESPONSE_UNIT,
    IncidentType.TRAFFIC_SPIKE: ResourceType.TRAFFIC_MANAGEMENT_UNIT,
}


class LayaAdapter:
    def __init__(
        self,
        mode: LayaMode = LayaMode.MOCK,
        *,
        cache: dict[str, NormalizedLayaResponse] | None = None,
        force_status: LayaStatus | None = None,
        latency_ms: float = 38.0,
    ) -> None:
        self.mode = mode
        self.cache: dict[str, NormalizedLayaResponse] = (
            cache if cache is not None else {}
        )
        self.force_status = force_status
        self.latency_ms = latency_ms

    @property
    def checkpoint(self) -> str:
        return CHECKPOINT

    @property
    def runtime(self) -> str:
        return RUNTIME if self.mode == LayaMode.LIVE else f"{RUNTIME}({self.mode.value})"

    def ask(self, state: LayaState) -> NormalizedLayaResponse:
        request = LayaRequest(state=state, questions=QUESTIONS)
        state_hash = hash_state(state)
        questions_hash = hash_questions(request)
        key = self._cache_key(state_hash, questions_hash)

        if self.force_status is not None:
            return NormalizedLayaResponse.failed(
                self.force_status,
                runtime=self.runtime,
                checkpoint=CHECKPOINT,
                router_model=ROUTER_MODEL,
                device=DEVICE,
                state_hash=state_hash,
                questions_hash=questions_hash,
                error_code=f"forced_{self.force_status.value}",
                latency_ms=self.latency_ms,
            )

        if self.mode == LayaMode.LIVE:
            return NormalizedLayaResponse.failed(
                LayaStatus.UNAVAILABLE,
                runtime=self.runtime,
                checkpoint=CHECKPOINT,
                router_model=ROUTER_MODEL,
                device=DEVICE,
                state_hash=state_hash,
                questions_hash=questions_hash,
                error_code="live_integration_phase3",
                latency_ms=0.0,
            )

        if self.mode == LayaMode.CACHE and key in self.cache:
            return self.cache[key]

        response = normalize(
            request,
            self._mock_answers(state),
            state_hash=state_hash,
            questions_hash=questions_hash,
            latency_ms=self.latency_ms,
        )
        if self.mode == LayaMode.CACHE:
            self.cache[key] = response
        return response

    # --- internals ----------------------------------------------------

    @staticmethod
    def _cache_key(state_hash: str, questions_hash: str) -> str:
        raw = "|".join([state_hash, questions_hash, CHECKPOINT, DEVICE, DTYPE])
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _mock_answers(state: LayaState) -> dict:
        """Deterministic proposer: same state → same answers (demo replay requirement)."""
        sev = (state.severity_prediction or "LOW").upper()
        sev_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}[sev]
        criticalish = sev_rank >= 2 and (
            (state.traffic_congestion_delta or 0) >= 0.4 or sev == "CRITICAL"
        )
        priority = "CRITICAL" if criticalish else ("HIGH" if sev_rank == 2 else sev)
        distribution = {
            label: (0.55 if label == priority else 0.45 / 3)
            for label in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        }
        total = sum(distribution.values())
        distribution = {k: round(v / total, 4) for k, v in distribution.items()}

        review = state.data_quality_score >= 0.5 or state.available_ambulances == 0
        resource = _RESOURCE_BY_TYPE[state.incident_type].value
        resource_dist = {r: 0.05 for r in [
            "ambulance", "fire_truck", "police_unit",
            "flood_response_unit", "traffic_management_unit",
        ]}
        resource_dist[resource] = 1.0 - sum(v for k, v in resource_dist.items() if k != resource)

        return {
            "priority": {
                "choice": priority,
                "confidence": distribution[priority],
                "answer_confidence": distribution[priority],
                "distribution": distribution,
            },
            "needs_human_review": {
                "noul": 0.73 if review else 0.24,
                "answer_confidence": 0.73 if review else 0.24,
            },
            "recommended_resource_type": {
                "choice": resource,
                "confidence": resource_dist[resource],
                "answer_confidence": resource_dist[resource],
                "distribution": resource_dist,
            },
        }


def suggested_priority(response: NormalizedLayaResponse) -> Priority | None:
    answer = response.answers.get("priority")
    if isinstance(answer, ChoiceAnswer):
        return Priority(answer.choice)
    return None


def suggested_needs_human_review(response: NormalizedLayaResponse) -> bool | None:
    answer = response.answers.get("needs_human_review")
    if isinstance(answer, NoulAnswer):
        return answer.noul >= 0.5
    return None


def recommended_resource_type(response: NormalizedLayaResponse) -> ResourceType | None:
    answer = response.answers.get("recommended_resource_type")
    if isinstance(answer, ChoiceAnswer):
        return ResourceType(answer.choice)
    return None


def answer_confidence_priority(response: NormalizedLayaResponse) -> float | None:
    answer = response.answers.get("priority")
    if isinstance(answer, ChoiceAnswer):
        return answer.answer_confidence
    return None
