"""ADIP Phase 0 serving app — FastAPI wrapper around DecisionService.

Endpoints:
  POST /decide            -> DecisionOutput (route, decision, explanation, latency)
  GET  /audit/{id}/replay -> recompute a stored decision; bit-for-bit match required
  GET  /healthz            -> liveness
  GET  /metrics           -> Prometheus (stage histograms, route counters)

Run: .venv-bench/bin/uvicorn serving.app:app --port 8100
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from adip.questions import PAYLOAD_VERSION

from .pipeline import DecisionService, replay

AUDIT_DB = Path(__file__).resolve().parent / "audit.db"

app = FastAPI(title="ADIP Decision Service", version="0.1.0-phase0")
svc = DecisionService(audit_path=AUDIT_DB)

# Metrics registry lock: uvicorn runs sync endpoints in a thread pool, and the
# bare `+=` / dict-write pairs below are not atomic (a lost increment silently
# under-reports route counts under load).
_METRICS_LOCK = threading.Lock()


def _authorized(request: Request) -> bool:
    """Bearer auth, opt-in via ADIP_API_TOKEN.

    Unset token = open dev mode (documented in serving/README). A set token is
    compared in constant time; /healthz and /metrics stay open for probes and
    scrapers, /decide and audit replay do not.
    """
    token = os.environ.get("ADIP_API_TOKEN", "")
    if not token:
        return True
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return secrets.compare_digest(value, token)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in ("/healthz", "/metrics") or _authorized(request):
        return await call_next(request)
    return JSONResponse(
        {"detail": "missing or invalid bearer token"},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


class DecideRequest(BaseModel):
    text: str = Field(min_length=5, max_length=8000)


class DecideResponse(BaseModel):
    decision_id: str
    route: str
    decision: dict
    explanation: str
    # privacy is what stage 1 actually did (redaction counts, method); without
    # this field the response_model silently dropped it and callers could not
    # see whether input was redacted
    privacy: dict
    latency_ms: dict


def _record_error(text: str, exc: Exception) -> None:
    """Audit-always: a decide that raised still lands in the audit table,
    marked ERROR, so 'every decision is replayable' has no silent hole."""
    try:
        from .pipeline import privacy_scan
        state = privacy_scan({"text": text})
        svc.audit.append({
            "decision_id": str(uuid.uuid4()),
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "text_redacted": state["text_redacted"],
            "route": "ERROR",
            "decision_json": json.dumps(
                {"error": type(exc).__name__, "message": str(exc)[:200]}),
            "stage_ms_json": "{}",
            "pipeline_ms": 0.0,
            "payload_version": PAYLOAD_VERSION,
        })
    except Exception:
        pass  # never mask the original failure


@app.post("/decide", response_model=DecideResponse)
def decide(req: DecideRequest, request: Request) -> DecideResponse:
    try:
        out = svc.decide(req.text)
    except Exception as exc:
        with _METRICS_LOCK:
            ERRORS_TOTAL.labels(route="ERROR").inc()
        _record_error(req.text, exc)
        raise HTTPException(status_code=500,
                            detail=f"decision failed: {type(exc).__name__}")
    with _METRICS_LOCK:
        DECISIONS_TOTAL.labels(route=out["route"]).inc()
        PIPELINE_MS.observe(out["latency_ms"]["pipeline"])
        for stage, ms in out["latency_ms"]["stages"].items():
            STAGE_MS.labels(stage=stage).observe(ms)
    return out


@app.get("/audit/{decision_id}/replay")
def audit_replay(decision_id: str) -> dict:
    try:
        result = replay(decision_id, audit_path=AUDIT_DB)
    except KeyError:
        raise HTTPException(status_code=404, detail="decision_id not found")
    if result.get("failed"):
        raise HTTPException(
            status_code=409,
            detail="decision failed (route=ERROR); nothing to replay — see stored error")
    if not result["matches"]:
        raise HTTPException(status_code=500, detail="REPLAY MISMATCH — audit integrity broken")
    return {"decision_id": decision_id, "replay_verified": True,
            "decision": result["stored"]}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# ---- Prometheus metrics (no prometheus-client dependency; minimal registry) --

class _Hist:
    """Single histogram; label_str empty for unlabeled metrics."""

    def __init__(self, name: str, doc: str, label_str: str = ""):
        self.name, self.doc, self.label_str = name, doc, label_str
        self.buckets = [5, 10, 25, 50, 75, 100, 150, 250, 500, 1000, 2500]
        self.count, self.sum = 0, 0.0
        self._bucket_counts = [0] * len(self.buckets)

    def observe(self, v: float) -> None:
        self.count += 1
        self.sum += v
        for i, b in enumerate(self.buckets):
            if v <= b:
                self._bucket_counts[i] += 1

    def _braces(self, le=None) -> str:
        inner = []
        if le is not None:
            inner.append(f'le="{le}"')
        if self.label_str:
            inner.append(self.label_str)
        return "{" + ",".join(inner) + "}" if inner else ""

    def render(self, with_help: bool = True) -> str:
        lines = []
        if with_help:
            lines += [f"# HELP {self.name} {self.doc}", f"# TYPE {self.name} histogram"]
        lines.append(f"{self.name}_count{self._braces()} {self.count}")
        lines.append(f"{self.name}_sum{self._braces()} {self.sum:.3f}")
        for b, c in zip(self.buckets, self._bucket_counts):
            lines.append(f'{self.name}_bucket{self._braces(le=b)} {c}')
        lines.append(f'{self.name}_bucket{self._braces(le="+Inf")} {self.count}')
        return "\n".join(lines) + "\n"


class _HistVec:
    """Histogram family with one label dimension (e.g. stage)."""

    def __init__(self, name: str, doc: str, label: str):
        self.name, self.doc, self.label = name, doc, label
        self.children: dict[tuple, _Hist] = {}

    def labels(self, **kw) -> _Hist:
        key = tuple(kw.values())
        if key not in self.children:
            label_str = ",".join(f'{k}="{v}"' for k, v in kw.items())
            self.children[key] = _Hist(self.name, self.doc, label_str)
        return self.children[key]

    def render(self) -> str:
        parts = []
        for h in self.children.values():
            parts.append(h.render(with_help=False))
        if not parts:
            return _Hist(self.name, self.doc).render()
        return (f"# HELP {self.name} {self.doc}\n# TYPE {self.name} histogram\n"
                + "".join(parts))


class _Counter:
    def __init__(self, name: str, doc: str):
        self.name, self.doc, self.values = name, doc, {}

    def labels(self, **kw):
        self._last = tuple(kw.values())
        return self

    def inc(self, n: int = 1) -> None:
        self.values[self._last] = self.values.get(self._last, 0) + n

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.doc}", f"# TYPE {self.name} counter"]
        for k, v in self.values.items():
            lines.append(f'{self.name}{{route="{k[0]}"}} {v}')
        return "\n".join(lines) + "\n"


DECISIONS_TOTAL = _Counter("adip_decisions_total", "Total decisions by policy route")
ERRORS_TOTAL = _Counter("adip_errors_total", "Decide calls that raised (5xx)")
PIPELINE_MS = _Hist("adip_pipeline_ms", "End-to-end pipeline latency (ms)")
STAGE_MS = _HistVec("adip_stage_ms", "Per-stage latency (ms)", "stage")


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    with _METRICS_LOCK:
        body = DECISIONS_TOTAL.render() + ERRORS_TOTAL.render() + \
            PIPELINE_MS.render() + STAGE_MS.render()
    return body + \
        "# HELP adip_pipeline_p50_ms live p50 from the in-process summary\n" + \
        "# TYPE adip_pipeline_p50_ms gauge\n" + \
        f'adip_pipeline_p50_ms {svc.summary()["pipeline_p50_ms"] or 0}\n'
