from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

GOLDEN_PATH = ROOT / "datasets/golden-set/golden-v2.0.json"


@pytest.fixture(scope="session")
def golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


class FakeAgent:
    """Stands in for laya.load(...): same predict() contract, no model."""

    def __init__(self, choice="billing", probs=None, urg=1.0, refund=0.92):
        self.choice = choice
        self.probs = probs or {"billing": 0.9, "technical": 0.05,
                               "sales": 0.03, "account": 0.02}
        self.urg = urg
        self.refund = refund

    def predict(self, text, questions):
        return {"answers": {
            "department": {"choice": self.choice, "probabilities": self.probs},
            "urgency": {"score": self.urg},
            "refund": {"noul": self.refund},
        }}


@pytest.fixture
def fake_agent(monkeypatch) -> FakeAgent:
    agent = FakeAgent()
    import serving.pipeline as pl
    monkeypatch.setattr(pl, "_AGENT", agent)
    return agent


@pytest.fixture
def svc(tmp_path, fake_agent):
    """DecisionService with a throwaway audit DB."""
    from serving.pipeline import DecisionService
    return DecisionService(audit_path=tmp_path / "audit.db")
