"""ADIP Phase 0 serving pipeline (blueprint section 3/4, stage budgets in section 10).

Six stages, each a pure-ish function over an explicit state dict; DecisionService
orchestrates, times every stage, and writes a replayable audit record to SQLite
(WAL). Model loading is lazy and shared; the model call is the only impure stage.

Design contract (blueprint section 3):
  privacy scan -> fairness screen -> typed decision -> policy router ->
  explanation -> audit (async-capable, off the latency-critical path in prod;
  inline in Phase 0 and reported separately).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PAYLOAD_VERSION = 2

# --------------------------------------------------------------------------
# Stage 1: privacy scan (v0: regex redaction; Presidio swap-in is Phase 1)
# --------------------------------------------------------------------------

_PATTERNS = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\w)")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("ORDER", re.compile(r"\b(?:order|invoice|ticket)\s*#?\s*([A-Z0-9-]{4,})\b", re.I)),
    ("PERSON", re.compile(r"\b(?:I'?m|I am|this is)\s+([A-Z][a-z]+ [A-Z][a-z]+)\b")),
]


def privacy_scan(state: dict, _cfg=None) -> dict:
    text = state["text"]
    redactions = []
    for name, pat in _PATTERNS:
        text, n = pat.subn(f"[{name}]", text)
        if n:
            redactions.append(f"{name}x{n}")
    # light language sniff for Router evidence logging (blueprint section 8.10)
    non_ascii = sum(1 for ch in text if ord(ch) > 127)
    state["text_redacted"] = text
    state["privacy"] = {
        "redactions": redactions,
        "non_ascii_ratio": round(non_ascii / max(len(text), 1), 4),
        "method": "regex-v0",
    }
    return state


# --------------------------------------------------------------------------
# Stage 2: fairness screen (Phase 0: non-ASCII route-evidence + null screen)
# --------------------------------------------------------------------------

def fairness_screen(state: dict, _cfg=None) -> dict:
    # Phase 0 screen: log language evidence (Router hook point, section 8.10);
    # counterfactual probes and group fairness land in Phase 1 (section 4.5).
    pr = state["privacy"]
    lang = "undecided"
    if pr["non_ascii_ratio"] > 0.15:
        lang = "non-en"
    state["fairness"] = {"lang_evidence": lang, "screen": "pass"}
    return state


# --------------------------------------------------------------------------
# Stage 3: typed decision (the only model-touching stage)
# --------------------------------------------------------------------------

_AGENT = None
_AGENT_LOCK = threading.Lock()


def _get_agent():
    global _AGENT
    if _AGENT is None:
        with _AGENT_LOCK:
            if _AGENT is None:
                import laya_mlx as laya
                _AGENT = laya.load("aac6fef/laya-mlx", dtype="float16", batch_size=16)
    return _AGENT


QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this request?",
        "criteria": {
            "billing": "invoices, payments, refunds, duplicate charges",
            "technical": "bugs, outages, integration failures",
            "sales": "new purchases, upgrades, pricing",
            "account": "login, password, profile, subscription status, data requests",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this request?",
        "criteria": ["not urgent", "soon", "critical"],
    },
    "refund": {
        "type": "noul",
        "instructions": "Does the customer ask for money back?",
    },
}


def typed_decision(state: dict, cfg: dict) -> dict:
    agent = _get_agent()
    result = agent.predict(state["text_redacted"], QUESTIONS)
    a = result["answers"]

    dep = a["department"]
    dist = dep.get("probabilities") or {}
    selected = dep.get("choice") or max(dist, key=dist.get)
    urg = a["urgency"]
    urg_score = float(urg.get("score", 0.0))
    urg_pred = min(2, max(0, round(urg_score)))
    ref_p = float(a["refund"].get("noul", 0.0))

    state["decision"] = {
        "department": selected,
        "department_dist": dist,
        "department_conf": float(dist.get(selected, 0.0)),
        "urgency": urg_pred,
        "urgency_score": urg_score,
        "refund_p": ref_p,
        # calibration recipe from evals/calibrate.py (v1.0 predictions, T fit
        # on 50 records out-of-fold; refit on a held-out set before external claims)
        "refund_p_calibrated": _apply_temperature(ref_p, 0.45),
    }
    return state


def _apply_temperature(p: float, T: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    z = math.log(p / (1.0 - p)) / T
    return round(1.0 / (1.0 + math.exp(-z)), 4)


# --------------------------------------------------------------------------
# Stage 4: policy router (blueprint section 4: AUTO / REVIEW / ESCALATE)
# --------------------------------------------------------------------------

CONF_AUTO = 0.60
CONF_REVIEW = 0.35


def policy_router(state: dict, cfg: dict) -> dict:
    d = state["decision"]
    reasons = []
    route = "AUTO"

    if d["department_conf"] < CONF_REVIEW:
        route, reasons = "ESCALATE", ["department_conf < 0.35"]
    elif d["department_conf"] < CONF_AUTO:
        route, reasons = "REVIEW", ["department_conf < 0.60"]

    if d["urgency"] == 2 and route == "AUTO":
        route, reasons = "REVIEW", reasons + ["urgency critical -> human confirm"]
    if d["refund_p_calibrated"] >= 0.5 and d["refund_p_calibrated"] < 0.7 and route == "AUTO":
        route, reasons = "REVIEW", reasons + ["refund 0.5..0.7 borderline"]

    state["policy"] = {"route": route, "reasons": reasons,
                       "thresholds": {"auto": CONF_AUTO, "review": CONF_REVIEW}}
    return state


# --------------------------------------------------------------------------
# Stage 5: explanation assembler (templates over distributions; no generation)
# --------------------------------------------------------------------------

def explanation(state: dict, cfg: dict) -> dict:
    d = state["decision"]
    pol = state["policy"]
    parts = [
        f"Routed to {d['department']} ({d['department_conf']:.0%} confidence; "
        f"alternatives: " + ", ".join(f"{c} {p:.0%}" for c, p in sorted(d["department_dist"].items(), key=lambda kv: -kv[1])[1:3]) + ").",
        f"Urgency level {d['urgency']} (expected score {d['urgency_score']:.2f}).",
        f"P(refund requested) = {d['refund_p']:.2f} (calibrated {d['refund_p_calibrated']:.2f}).",
        f"Policy route: {pol['route']}" + (f" — {', '.join(pol['reasons'])}" if pol["reasons"] else "."),
    ]
    state["explanation"] = {"text": " ".join(parts), "method": "template+v0"}
    return state


# --------------------------------------------------------------------------
# Stage 6: audit log (SQLite WAL; replay = recompute decision from stored text)
# --------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT UNIQUE NOT NULL,
    ts_utc TEXT NOT NULL,
    text_redacted TEXT NOT NULL,
    route TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    stage_ms_json TEXT NOT NULL,
    pipeline_ms REAL NOT NULL,
    payload_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts_utc);
"""


class AuditLog:
    def __init__(self, path: str | Path):
        self._path = str(path)
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._path, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.executescript(_SCHEMA)
            self._local.conn = conn
        return self._local.conn

    def append(self, record: dict) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO decisions "
            "(decision_id, ts_utc, text_redacted, route, decision_json, "
            "stage_ms_json, pipeline_ms, payload_version) VALUES (?,?,?,?,?,?,?,?)",
            (record["decision_id"], record["ts_utc"], record["text_redacted"],
             record["route"], record["decision_json"], record["stage_ms_json"],
             record["pipeline_ms"], record["payload_version"]),
        )
        conn.commit()

    def fetch(self, decision_id: str) -> dict | None:
        row = self._conn().execute(
            "SELECT decision_id, ts_utc, text_redacted, route, decision_json, "
            "stage_ms_json, pipeline_ms, payload_version FROM decisions WHERE decision_id=?",
            (decision_id,)).fetchone()
        if not row:
            return None
        keys = ["decision_id", "ts_utc", "text_redacted", "route", "decision_json",
                "stage_ms_json", "pipeline_ms", "payload_version"]
        return dict(zip(keys, row))


# --------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------

STAGES = [
    ("privacy", privacy_scan),
    ("fairness", fairness_screen),
    ("decision", typed_decision),
    ("policy", policy_router),
    ("explanation", explanation),
]


class DecisionService:
    def __init__(self, audit_path: str | Path = "serving/audit.db"):
        self.audit = AuditLog(audit_path)
        self.stage_ms: dict[str, list[float]] = {name: [] for name, _ in STAGES}
        self.pipeline_ms: list[float] = []
        self._lock = threading.Lock()

    def decide(self, text: str) -> dict:
        state: dict = {"text": text, "decision_id": str(uuid.uuid4())}
        stage_ms = {}
        t0 = time.perf_counter()
        for name, fn in STAGES:
            ts = time.perf_counter()
            state = fn(state, {})
            stage_ms[name] = round((time.perf_counter() - ts) * 1000, 3)
        pipeline_ms = round((time.perf_counter() - t0) * 1000, 3)

        record = {
            "decision_id": state["decision_id"],
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "text_redacted": state["text_redacted"],
            "route": state["policy"]["route"],
            "decision_json": json.dumps(state["decision"], sort_keys=True),
            "stage_ms_json": json.dumps(stage_ms, sort_keys=True),
            "pipeline_ms": pipeline_ms,
            "payload_version": PAYLOAD_VERSION,
        }
        self.audit.append(record)

        with self._lock:
            for name, ms in stage_ms.items():
                self._safe_append(self.stage_ms[name], ms)
            self._safe_append(self.pipeline_ms, pipeline_ms)

        return {
            "decision_id": state["decision_id"],
            "route": state["policy"]["route"],
            "decision": state["decision"],
            "explanation": state["explanation"]["text"],
            "privacy": state["privacy"],
            "latency_ms": {"pipeline": pipeline_ms, "stages": stage_ms},
        }

    @staticmethod
    def _safe_append(lst: list, value: float, cap: int = 10_000) -> None:
        if len(lst) < cap:
            lst.append(value)

    def summary(self) -> dict:
        def pct(xs, p):
            s = sorted(xs)
            return round(s[int(p / 100 * (len(s) - 1))], 2) if s else None
        return {
            "n": len(self.pipeline_ms),
            "pipeline_p50_ms": pct(self.pipeline_ms, 50),
            "pipeline_p95_ms": pct(self.pipeline_ms, 95),
            "stage_p50_ms": {k: pct(v, 50) for k, v in self.stage_ms.items()},
        }


def replay(decision_id: str, audit_path: str | Path = "serving/audit.db") -> dict:
    """Recompute a decision from the stored redacted text; bit-for-bit match
    proves the audit row fully determines the decision (blueprint section 11)."""
    svc = DecisionService.__new__(DecisionService)
    svc.audit = AuditLog(audit_path)
    rec = svc.audit.fetch(decision_id)
    if not rec:
        raise KeyError(decision_id)
    state: dict = {"text": rec["text_redacted"], "decision_id": rec["decision_id"]}
    for name, fn in STAGES:
        if name in ("privacy",):  # redaction already applied on stored text
            state = fn(state, {})
            state["text_redacted"] = state["text"]  # idempotent on clean text
            continue
        state = fn(state, {})
    return {
        "matches": state["decision"] == json.loads(rec["decision_json"]),
        "stored": json.loads(rec["decision_json"]),
        "recomputed": state["decision"],
    }
