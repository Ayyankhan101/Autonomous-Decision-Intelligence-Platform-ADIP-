"""ADIP Phase 0 serving app — FastAPI wrapper around DecisionService.

Endpoints:
  POST /decide            -> DecisionOutput (route, decision, explanation, latency)
  GET  /audit/{id}/replay -> recompute a stored decision; bit-for-bit match required
  GET  /healthz            -> liveness
  GET  /metrics           -> Prometheus (stage histograms, route counters)

Run: .venv-bench/bin/uvicorn serving.app:app --port 8100
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .pipeline import DecisionService, replay

AUDIT_DB = Path(__file__).resolve().parent / "audit.db"

app = FastAPI(title="ADIP Decision Service", version="0.1.0-phase0")
svc = DecisionService(audit_path=AUDIT_DB)


class DecideRequest(BaseModel):
    text: str = Field(min_length=5, max_length=8000)


class DecideResponse(BaseModel):
    decision_id: str
    route: str
    decision: dict
    explanation: str
    latency_ms: dict


@app.post("/decide", response_model=DecideResponse)
def decide(req: DecideRequest) -> DecideResponse:
    out = svc.decide(req.text)
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
PIPELINE_MS = _Hist("adip_pipeline_ms", "End-to-end pipeline latency (ms)")
STAGE_MS = _HistVec("adip_stage_ms", "Per-stage latency (ms)", "stage")


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return DECISIONS_TOTAL.render() + PIPELINE_MS.render() + STAGE_MS.render() + \
        "# HELP adip_pipeline_p50_ms live p50 from the in-process summary\n" + \
        "# TYPE adip_pipeline_p50_ms gauge\n" + \
        f'adip_pipeline_p50_ms {svc.summary()["pipeline_p50_ms"] or 0}\n'
