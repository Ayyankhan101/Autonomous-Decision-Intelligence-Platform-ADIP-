"""Model wrapper (plan Phase 2): stable internal API with timeout handling, error
containment, measured latency, status + model version on every call."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

from jevcity.schemas import AnomalyOutput, ModelOutput, ModelStatus

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="jevcity-model")
_DEFAULT_TIMEOUT_S = 0.5


def _timed_call(fn: Any, args: tuple, kwargs: dict, timeout_s: float) -> Any:
    future = _POOL.submit(fn, *args, **kwargs)
    return future.result(timeout=timeout_s)


class ModelWrapper:
    def __init__(self, inner: Any, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self.inner = inner
        self.timeout_s = timeout_s

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def version(self) -> str:
        return self.inner.version

    def predict(self, *args: Any, **kwargs: Any) -> ModelOutput:
        t0 = time.perf_counter()
        try:
            out = _timed_call(self.inner.predict, args, kwargs, self.timeout_s)
        except FuturesTimeout:
            return ModelOutput.failed(
                self.name, self.version, ModelStatus.TIMEOUT,
                error_code="MODEL_TIMEOUT",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception:
            return ModelOutput.failed(
                self.name, self.version, ModelStatus.ERROR,
                error_code="MODEL_EXCEPTION",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        return out.model_copy(
            update={"latency_ms": round((time.perf_counter() - t0) * 1000, 3)}
        )


class AnomalyWrapper:
    def __init__(self, inner: Any, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self.inner = inner
        self.timeout_s = timeout_s

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def version(self) -> str:
        return self.inner.version

    def predict(self, *args: Any, **kwargs: Any) -> AnomalyOutput:
        try:
            return _timed_call(self.inner.predict, args, kwargs, self.timeout_s)
        except (FuturesTimeout, Exception):
            return AnomalyOutput(
                data_quality_anomaly=True,
                data_quality_score=1.0,
                situational_anomaly=False,
                reasons=["anomaly_model_failure"],
            )
