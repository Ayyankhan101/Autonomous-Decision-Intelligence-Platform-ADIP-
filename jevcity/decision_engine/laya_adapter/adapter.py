"""Laya adapter (plan §5.4): proposer only — no DB access, no audit writes, no resource
assignment, no invariant overrides. Modes: mock (tests/demo), cache (deterministic replay),
live (Phase 3 — in-process laya_mlx predict, thread-timeout guarded, fail-closed)."""
from __future__ import annotations

import hashlib
import threading
import time

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

from .normalize import (
    CHECKPOINT,
    DEVICE,
    ROUTER_MODEL,
    RUNTIME,
    hash_questions,
    normalize,
    to_raw,
)
from .questions import QUESTIONS
from .state_builder import hash_state
from .state_text import render_state

DTYPE = "float16"
LIVE_TIMEOUT_S = 10.0
LIVE_MAX_ATTEMPTS = 2
LIVE_BREAKER_THRESHOLD = 3
LIVE_BREAKER_PROBE_EVERY = 5

_QUESTIONS_JSON = {k: v.model_dump(mode="json") for k, v in QUESTIONS.items()}
_LIVE_AGENT: dict[str, object] = {}


def _live_agent() -> object:
    """Load (once) and return the in-process laya_mlx agent for the frozen checkpoint."""
    agent = _LIVE_AGENT.get("agent")
    if agent is None:
        import laya_mlx as laya

        agent = laya.load(CHECKPOINT, dtype=DTYPE, batch_size=8)
        _LIVE_AGENT["agent"] = agent
    return agent

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
        live_timeout_s: float = LIVE_TIMEOUT_S,
    ) -> None:
        self.mode = mode
        self.cache: dict[str, NormalizedLayaResponse] = (
            cache if cache is not None else {}
        )
        self.force_status = force_status
        self.latency_ms = latency_ms
        self.live_timeout_s = live_timeout_s
        self._live_failures = 0
        self._live_blocked = 0

    @property
    def checkpoint(self) -> str:
        return CHECKPOINT

    @property
    def runtime(self) -> str:
        return RUNTIME if self.mode == LayaMode.LIVE else f"{RUNTIME}({self.mode.value})"

    def health(self) -> dict[str, str | bool | float]:
        """Internal readiness probe — no API endpoint (contracts frozen at 16)."""
        return {
            "mode": self.mode.value,
            "runtime": RUNTIME,
            "checkpoint": CHECKPOINT,
            "router_model": ROUTER_MODEL,
            "device": DEVICE,
            "dtype": DTYPE,
            "live_agent_loaded": "agent" in _LIVE_AGENT,
            "live_timeout_s": self.live_timeout_s,
            "breaker_open": self._live_failures >= LIVE_BREAKER_THRESHOLD,
        }

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
            return self._live_ask(request, state, state_hash, questions_hash)

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

    def _live_ask(
        self,
        request: LayaRequest,
        state: LayaState,
        state_hash: str,
        questions_hash: str,
    ) -> NormalizedLayaResponse:
        """LIVE path: breaker → retries → thread-timeout predict → to_raw → normalize."""
        if not self._breaker_allows():
            return NormalizedLayaResponse.failed(
                LayaStatus.UNAVAILABLE,
                runtime=self.runtime,
                checkpoint=CHECKPOINT,
                router_model=ROUTER_MODEL,
                device=DEVICE,
                state_hash=state_hash,
                questions_hash=questions_hash,
                error_code="circuit_open",
                latency_ms=0.0,
            )
        result, latency_ms, error = self._live_attempts(state)
        self._breaker_record(transport_ok=error is None)
        if error is not None:
            if isinstance(error, TimeoutError):
                return NormalizedLayaResponse.failed(
                    LayaStatus.TIMEOUT,
                    runtime=self.runtime,
                    checkpoint=CHECKPOINT,
                    router_model=ROUTER_MODEL,
                    device=DEVICE,
                    state_hash=state_hash,
                    questions_hash=questions_hash,
                    error_code="live_timeout",
                    latency_ms=self.live_timeout_s * 1000.0,
                )
            return NormalizedLayaResponse.failed(
                LayaStatus.UNAVAILABLE,
                runtime=self.runtime,
                checkpoint=CHECKPOINT,
                router_model=ROUTER_MODEL,
                device=DEVICE,
                state_hash=state_hash,
                questions_hash=questions_hash,
                error_code=f"live_error:{type(error).__name__}",
                latency_ms=0.0,
            )
        raw = to_raw(result)
        if raw is None:
            return NormalizedLayaResponse.failed(
                LayaStatus.INVALID_RESPONSE,
                runtime=self.runtime,
                checkpoint=CHECKPOINT,
                router_model=ROUTER_MODEL,
                device=DEVICE,
                state_hash=state_hash,
                questions_hash=questions_hash,
                error_code="raw_extract_failed",
                latency_ms=latency_ms,
            )
        return normalize(
            request,
            raw,
            state_hash=state_hash,
            questions_hash=questions_hash,
            latency_ms=latency_ms,
        )

    def _breaker_allows(self) -> bool:
        """Call-count circuit breaker: OPEN after threshold failures, probe every Nth blocked call."""
        if self._live_failures < LIVE_BREAKER_THRESHOLD:
            return True
        self._live_blocked += 1
        return self._live_blocked % LIVE_BREAKER_PROBE_EVERY == 0

    def _breaker_record(self, transport_ok: bool) -> None:
        if transport_ok:
            self._live_failures = 0
            self._live_blocked = 0
        else:
            self._live_failures += 1

    def _live_attempts(self, state: LayaState) -> tuple[dict | None, float, Exception | None]:
        """Retry policy: TimeoutError retried once (LIVE_MAX_ATTEMPTS total); other errors fail fast."""
        last_error: Exception = TimeoutError("live predict never attempted")
        for _ in range(LIVE_MAX_ATTEMPTS):
            try:
                result, latency_ms = self._live_call(state)
                return result, latency_ms, None
            except TimeoutError as exc:
                last_error = exc
            except Exception as exc:
                return None, 0.0, exc
        return None, 0.0, last_error

    def _live_call(self, state: LayaState) -> tuple[dict, float]:
        """Run laya_mlx predict on a daemon thread; raise TimeoutError on overrun."""
        box: dict = {}
        done = threading.Event()

        def _run() -> None:
            t0 = time.perf_counter()
            try:
                agent = _live_agent()
                box["result"] = agent.predict(render_state(state), _QUESTIONS_JSON)
                box["latency_ms"] = (time.perf_counter() - t0) * 1000.0
            except Exception as exc:
                box["error"] = exc
            finally:
                done.set()

        threading.Thread(target=_run, daemon=True, name="laya-live-predict").start()
        if not done.wait(timeout=self.live_timeout_s):
            raise TimeoutError(f"live predict exceeded {self.live_timeout_s}s")
        if "error" in box:
            raise box["error"]
        return box["result"], box["latency_ms"]

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
