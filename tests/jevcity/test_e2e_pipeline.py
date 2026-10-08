"""Phase 6 integration tests.

F1: one-pass integration — replayed history -> live event -> ML triad -> Laya ->
guardrail -> dashboard payloads -> audit chain (plan: "an end-to-end test where a
replayed history feeds a live event through the ML models, Laya, guardrail,
dashboard, and audit trail in one pass").

F4: latency-budget degradation composite — forced Laya timeout across decision,
dashboard, and audit surfaces (plan §6 "Latency test budget").
"""
from __future__ import annotations

from jevcity.schemas.decision import DecisionState, Priority


def test_replay_history_then_live_event_one_pass(client):
    # 1. Replayed history (plan item 1: deterministic recording as secondary source).
    r = client.post(
        "/api/simulation/start",
        json={
            "session_seed": 42,
            "scenario_seed": 7,
            "recording": "sim-session-v1.jsonl",
            "speed": 5.0,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["decision_ids"]) >= 6
    replayed = list(body["decision_ids"])

    state = client.get("/api/state").json()
    assert state["incident_count"] >= 6
    assert state["decision_count"] == len(replayed)
    incidents_before = state["incident_count"]

    # 2. Live event on top of the replayed history.
    r = client.post(
        "/api/simulation/incident",
        json={
            "incident_type": "accident",
            "zone": "east",
            "severity": "severe",
            "source_id": "e2e-sensor",
            "notes": "multi-vehicle pileup",
        },
    )
    assert r.status_code == 200
    inc_body = r.json()
    decision_id = inc_body["decision_ids"][-1]
    incident_id = inc_body["incident_id"]
    assert decision_id not in replayed

    # 3. ML triad ran with ok status and versioned contracts.
    dec = client.get(f"/api/decisions/{decision_id}").json()
    assert dec["signals"]["severity"]["status"] == "ok"
    assert dec["signals"]["traffic"]["status"] == "ok"
    assert 0.0 <= dec["signals"]["severity"]["confidence"] <= 1.0
    assert 0.0 <= dec["signals"]["traffic"]["confidence"] <= 1.0
    assert dec["incident_id"] == incident_id

    # 4. Laya advisory: valid typed output, distribution over all four priorities.
    laya = dec["laya"]
    assert laya["status"] == "ok"
    assert laya["suggested_priority"] in {p.value for p in Priority}
    dist = laya["distribution"]
    assert set(dist) == {p.value for p in Priority}
    assert abs(sum(dist.values()) - 1.0) < 1e-6
    assert 0.0 <= laya["answer_confidence_priority"] <= 1.0
    assert laya["checkpoint"] == "aac6fef/laya-typed-decisions-mlx"
    assert laya["final_decision_source"] in {
        "policy_finalized",
        "laya_fallback_policy_only",
        "laya_proposed",
    }

    # 5. Guardrail produced a complete, finalized decision record.
    assert dec["state"] in {s.value for s in DecisionState}
    assert dec["priority"] in {p.value for p in Priority}
    assert dec["matched_rules"]
    assert dec["reasons"]
    assert isinstance(laya.get("guardrail_applied"), bool)

    # 6. Dashboard payloads reflect the same run without drift.
    state = client.get("/api/state").json()
    assert state["decision_count"] == len(replayed) + 1
    assert state["incident_count"] == incidents_before + 1
    assert state["laya_mode"] == "mock"
    assert state["last_laya_status"] == "ok"
    assert len(client.get("/api/resources").json()["resources"]) >= 1
    incidents = client.get("/api/incidents").json()["incidents"]
    assert any(i["incident_id"] == incident_id for i in incidents)
    detail = client.get(f"/api/incidents/{incident_id}").json()
    assert detail["latest_decision"]["decision_id"] == decision_id

    # 7. Audit trail: decision entry carries model versions + Laya metadata, hash chain intact.
    entries = client.get("/api/audit?limit=300").json()["entries"]
    assert [e["decision_id"] for e in entries if e["decision_id"] in set(replayed) | {decision_id}]
    entry = next(e for e in entries if e["decision_id"] == decision_id)
    assert entry["action"] == "DECISION_EMITTED"
    assert entry["model_versions"]["severity"] == "sev-gb-1.0.0"
    assert entry["model_versions"]["traffic"] == "traffic-gbr-1.0.0"
    assert entry["model_versions"]["anomaly"] == "anom-ml-1.0.0"
    laya_meta = entry["laya"]
    assert laya_meta["laya_checkpoint"] == "aac6fef/laya-typed-decisions-mlx"
    assert laya_meta["laya_status"] == "ok"
    assert laya_meta["laya_suggested_priority"] == laya["suggested_priority"]
    assert laya_meta["laya_state_hash"].startswith("sha256:")
    assert laya_meta["laya_questions_version"] == "q-0.1.0"

    # Entries are returned newest-first: each newer entry's previous_hash links to the
    # older entry's hash, and the oldest entry links to genesis.
    assert entries[-1]["previous_hash"] == "sha256:genesis"
    for newer, older in zip(entries, entries[1:]):
        assert newer["previous_hash"] == older["entry_hash"]


def test_laya_timeout_degradation_composite(engine, client):
    """Phase 6 (F4): when Laya exceeds the latency budget (forced timeout), all three
    surfaces agree — fallback decision produced, dashboard marks the degraded state,
    audit records the timeout (plan §6 "Latency test budget")."""
    from model_stubs import FixedSeverity, FixedTraffic

    from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
    from jevcity.schemas import IncidentType, LayaMode, LayaStatus, Zone

    engine.severity = FixedSeverity("MEDIUM", 0.9)
    engine.traffic = FixedTraffic(0.3, 0.9)
    engine.adapter = LayaAdapter(mode=LayaMode.LIVE, force_status=LayaStatus.TIMEOUT)

    r = client.post(
        "/api/simulation/incident",
        json={
            "incident_type": IncidentType.ACCIDENT.value,
            "zone": Zone.NORTH.value,
            "source_id": "budget-sensor",
            "notes": "minor collision",
        },
    )
    assert r.status_code == 200
    decision_id = r.json()["decision_ids"][-1]

    # (1) A fallback decision was still produced (never a crash, never AUTO from Laya).
    dec = client.get(f"/api/decisions/{decision_id}").json()
    assert dec["state"] in {"MODEL_DEGRADED", "HOLD_FOR_HUMAN"}
    assert dec["state"] != "AUTO_APPROVED"
    assert dec["priority"] in {p.value for p in Priority}
    assert dec["laya"]["status"] == "timeout"
    assert dec["laya"]["final_decision_source"] == "fallback_rule"

    # (2) Dashboard state marks the degraded Laya run.
    state = client.get("/api/state").json()
    assert state["last_laya_status"] == "timeout"
    assert state["laya_mode"] == "live"

    # (3) Audit records the timeout with fallback metadata.
    entry = next(
        e
        for e in client.get("/api/audit?limit=300").json()["entries"]
        if e["decision_id"] == decision_id
    )
    meta = entry["laya"]
    assert meta["laya_status"] == "timeout"
    assert meta["laya_fallback_used"] is True
    assert meta["laya_final_decision_source"] == "fallback_rule"
