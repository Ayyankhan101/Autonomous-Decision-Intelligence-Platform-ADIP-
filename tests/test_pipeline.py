"""Pipeline stages without the model: redaction, routing, audit, replay."""

from __future__ import annotations

import json

import pytest

from adip.config import (CONF_AUTO, CONF_REVIEW, REFUND_REVIEW_HI,
                         REFUND_TEMPERATURE, REFUND_THRESHOLD)
from serving.pipeline import replay
from tests.conftest import FakeAgent


@pytest.fixture
def agent_factory(monkeypatch):
    """Inject a fake model into the lazy loader; restored after each test."""
    def _make(**kwargs) -> FakeAgent:
        agent = FakeAgent(**kwargs)
        monkeypatch.setattr("serving.pipeline._AGENT", agent)
        return agent
    return _make


def test_decide_returns_contract_shape(svc):
    out = svc.decide("Charged twice for order #A1B2C3, please refund")
    assert set(out) == {"decision_id", "route", "decision", "explanation",
                        "privacy", "latency_ms"}
    assert out["route"] in {"AUTO", "REVIEW", "ESCALATE"}
    d = out["decision"]
    assert set(d) == {"department", "department_dist", "department_dist_raw",
                      "department_conf", "urgency", "urgency_score",
                      "refund_p", "refund_p_calibrated"}
    assert out["privacy"]["method"] == "regex-v0"
    assert out["latency_ms"]["pipeline"] >= 0
    assert out["explanation"].startswith("Routed to billing")


def test_email_and_order_are_redacted_before_model_and_in_audit(svc):
    out = svc.decide("email me at jane.doe@example.com about invoice #INV-99")
    red = out["privacy"]["redactions"]
    assert any(r.startswith("EMAIL") for r in red)
    assert any(r.startswith("ORDER") for r in red)
    row = svc.audit.fetch(out["decision_id"])
    assert "jane.doe@example.com" not in row["text_redacted"]
    assert "[EMAIL]" in row["text_redacted"]


def test_router_review_when_below_conf_auto(svc, agent_factory):
    # raw 0.50 -> calibrated 0.64 would be AUTO; 0.45 -> 0.55 lands in the
    # REVIEW band once adip.config.DEPT_TEMPERATURE is applied to the dist
    agent_factory(probs={"billing": 0.45, "technical": 0.35,
                         "sales": 0.10, "account": 0.10})
    out = svc.decide("invoice question")
    assert CONF_REVIEW <= out["decision"]["department_conf"] < CONF_AUTO
    assert out["route"] == "REVIEW"
    assert f"department_conf < {CONF_AUTO:.2f}" in out["explanation"]


def test_router_escalate_when_below_conf_review(svc, agent_factory):
    agent_factory(probs={"billing": 0.30, "technical": 0.30,
                         "sales": 0.20, "account": 0.20})
    out = svc.decide("ambiguous")
    assert out["route"] == "ESCALATE"
    assert f"department_conf < {CONF_REVIEW:.2f}" in out["explanation"]


def test_critical_urgency_is_never_auto(svc, agent_factory):
    agent_factory(urg=2.0)
    out = svc.decide("site down, production halted")
    assert out["decision"]["urgency"] == 2
    assert out["route"] == "REVIEW"
    assert "urgency critical" in out["explanation"]


def test_borderline_refund_is_never_auto(svc, agent_factory):
    agent_factory(refund=0.55)
    out = svc.decide("can i get my money back")
    d = out["decision"]
    assert REFUND_TEMPERATURE != 1.0  # calibration is actually applied
    assert d["refund_p_calibrated"] != d["refund_p"]
    assert REFUND_THRESHOLD <= d["refund_p_calibrated"] < REFUND_REVIEW_HI
    assert out["route"] == "REVIEW"
    assert "borderline" in out["explanation"]


def test_department_confidence_is_calibrated(svc, agent_factory):
    from adip.config import DEPT_TEMPERATURE
    agent_factory(probs={"billing": 0.50, "technical": 0.30,
                         "sales": 0.10, "account": 0.10})
    out = svc.decide("invoice question")
    d = out["decision"]
    assert DEPT_TEMPERATURE != 1.0
    # calibrated dist is shipped; raw kept for provenance; argmax preserved
    assert d["department_dist"] != d["department_dist_raw"]
    assert max(d["department_dist"], key=d["department_dist"].get) == \
        max(d["department_dist_raw"], key=d["department_dist_raw"].get) == "billing"
    assert abs(d["department_conf"] - max(d["department_dist"].values())) < 1e-9
    assert sum(d["department_dist"].values()) == pytest.approx(1.0)


def test_confident_auto_path_stays_auto(svc, agent_factory):
    agent_factory(urg=0.0, refund=0.99)
    out = svc.decide("how do I reset my password")
    assert out["route"] == "AUTO"


def test_replay_is_reproducible_from_audit_row(svc):
    out = svc.decide("my password reset link is broken")
    result = replay(out["decision_id"], audit_path=svc.audit._path)
    assert result["matches"] is True
    assert result["recomputed"] == json.loads(
        svc.audit.fetch(out["decision_id"])["decision_json"])


def test_replay_unknown_id_raises(svc):
    with pytest.raises(KeyError):
        replay("no-such-id", audit_path=svc.audit._path)


def test_summary_percentiles_use_shared_stat(svc):
    for _ in range(5):
        svc.decide("repeat load sample")
    s = svc.summary()
    assert s["n"] == 5
    assert s["pipeline_p50_ms"] is not None and s["pipeline_p95_ms"] is not None
    assert set(s["stage_p50_ms"]) == {"privacy", "fairness", "decision",
                                      "policy", "explanation"}
