"""Live laya_mlx contract verification (Phase 3 C6).

Closes PHASE0_SIGNOFF item 18 (upstream answer_confidence does not exist —
derivation is the contract, ERRATA C2) and the item 17 note (question schema
accepted by the real agent). Marked model + laya_live: runs only in the macOS
job's LayA live smoke step, never on the ubuntu PR tier.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jevcity.decision_engine.laya_adapter.adapter import DTYPE, LayaAdapter
from jevcity.decision_engine.laya_adapter.normalize import CHECKPOINT, normalize, to_raw
from jevcity.decision_engine.laya_adapter.questions import QUESTIONS
from jevcity.decision_engine.laya_adapter.state_text import render_state
from jevcity.schemas import LayaMode, LayaRequest, LayaState, LayaStatus

pytestmark = [pytest.mark.model, pytest.mark.laya_live]

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "jevcity_decisions.jsonl"


def _fixture_state() -> LayaState:
    row = json.loads(FIXTURES.read_text().splitlines()[0])
    return LayaState.model_validate(row["state"])


def test_upstream_answers_have_no_answer_confidence():
    import laya_mlx as laya

    agent = laya.load(CHECKPOINT, dtype=DTYPE, batch_size=8)
    questions = {k: v.model_dump(mode="json") for k, v in QUESTIONS.items()}
    result = agent.predict(render_state(_fixture_state()), questions)
    answers = result["answers"]
    assert set(answers) == {"priority", "needs_human_review", "recommended_resource_type"}
    for key, fields in {
        "priority": {"action", "choice", "confidence", "probabilities", "type"},
        "needs_human_review": {"action", "confidence", "noul", "type"},
        "recommended_resource_type": {"action", "choice", "confidence", "probabilities", "type"},
    }.items():
        assert set(answers[key]) == fields, key
        assert "answer_confidence" not in answers[key], key
    raw = to_raw(result)
    assert raw is not None
    request = LayaRequest(state=_fixture_state(), questions=QUESTIONS)
    normalized = normalize(
        request, raw, state_hash="sha256:live", questions_hash="sha256:live",
        latency_ms=1.0,
    )
    assert normalized.status is LayaStatus.OK
    assert 0.0 <= normalized.answers["priority"].answer_confidence <= 1.0
    assert isinstance(result.get("model"), str) and result["model"]


def test_live_adapter_end_to_end_deterministic():
    adapter = LayaAdapter(mode=LayaMode.LIVE)
    state = _fixture_state()
    a = adapter.ask(state)
    b = adapter.ask(state)
    assert a.status is LayaStatus.OK
    assert b.status is LayaStatus.OK
    assert a.answers["priority"].choice == b.answers["priority"].choice
    assert a.answers["priority"].distribution == b.answers["priority"].distribution
    assert a.answers["recommended_resource_type"].choice == (
        b.answers["recommended_resource_type"].choice
    )
    assert a.state_hash == b.state_hash
    assert a.latency_ms > 0.0
    health = adapter.health()
    assert health["live_agent_loaded"] is True
    assert health["breaker_open"] is False
