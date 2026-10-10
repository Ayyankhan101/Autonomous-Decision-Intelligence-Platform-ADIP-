"""Vision schemas + severity-mismatch soft flag (Tasks 5-7)."""
from datetime import datetime, timezone

from jevcity.ingestion.vision_findings import vision_findings
from jevcity.schemas import (
    DamageSeverity,
    IncidentRecord,
    SceneType,
    SeverityHint,
    VisionFacts,
    VisionMode,
    VisionStatus,
)


def _incident(severity: SeverityHint) -> IncidentRecord:
    return IncidentRecord(
        incident_id="inc-1", incident_type="accident", zone="north",
        first_seen_simulated=datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc),
        latest_simulated=datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc),
        validation_status="valid", severity_hint=severity,
    )


def _facts(damage: DamageSeverity) -> VisionFacts:
    return VisionFacts(
        image_sha256="ab" * 32, scene=SceneType.ACCIDENT, objects=["car"],
        damage_severity=damage, injuries_visible=True,
        confidence={"scene": 0.9}, model_id="mock-vlm", model_version="0.1.0",
        mode=VisionMode.MOCK, latency_ms=1.0,
    )


def test_mismatch_raises_soft_flag():
    inc = _incident(SeverityHint.MINOR)
    findings = vision_findings(_facts(DamageSeverity.HIGH), inc)
    assert [f.code for f in findings] == ["severity_mismatch_vision"]
    assert findings[0].severity == "soft"


def test_agreement_or_unknown_raises_nothing():
    for sev, dmg in ((SeverityHint.MODERATE, DamageSeverity.MEDIUM),
                     (SeverityHint.SEVERE, DamageSeverity.HIGH),
                     (SeverityHint.MINOR, DamageSeverity.LOW),
                     (SeverityHint.MINOR, DamageSeverity.UNKNOWN)):
        assert vision_findings(_facts(dmg), _incident(sev)) == []


def test_unavailable_facts_raise_nothing():
    failed = VisionFacts.failed(
        image_sha256="ab" * 32, mode=VisionMode.LIVE, model_id="qwen",
        model_version="4bit", latency_ms=1.0, status=VisionStatus.UNAVAILABLE,
        error_code="timeout",
    )
    assert vision_findings(failed, _incident(SeverityHint.MINOR)) == []


def test_incident_record_accepts_optional_vision():
    inc = _incident(SeverityHint.MINOR)
    assert inc.vision is None
    assert inc.severity_hint is SeverityHint.MINOR
    inc.vision = None  # additive default; extra=forbid unaffected


def test_attach_image_sets_incident_and_writes_audit_on_sim_clock():
    from jevcity.api.app import build_engine
    from jevcity.schemas import IncidentType, Zone

    engine = build_engine()
    engine.simulation.start(42, 7)
    engine.simulation.inject_incident(
        IncidentType.ACCIDENT, Zone.NORTH, SeverityHint.MINOR
    )
    records = engine.process_pending()
    incident_id = records[0].incident_id

    att = engine.attach_image(incident_id, _facts(DamageSeverity.HIGH))
    assert engine.simulation.incidents[incident_id].vision is att
    assert att.latest_decision_id == records[0].decision_id
    assert [f.code for f in att.soft_findings] == ["severity_mismatch_vision"]

    entries = [e for e in engine.audit.entries(limit=200)
               if e.action == "VISION_ATTACHED"]
    assert len(entries) == 1
    assert entries[0].incident_id == incident_id
    assert entries[0].timestamp is not None  # sim clock, passed explicitly
    # chain still valid after the new entry
    assert engine.audit.validate_chain()


def test_attach_unknown_incident_raises_key_error():
    from jevcity.api.app import build_engine

    engine = build_engine()
    try:
        engine.attach_image("inc-does-not-exist", _facts(DamageSeverity.LOW))
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


# --- API routes (Task 7) -------------------------------------------------

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app

PNG_B64 = base64.b64encode(Path("fixtures/vision/scene.png").read_bytes()).decode()


def _started_client():
    engine = build_engine()
    client = TestClient(create_app(engine))
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    return engine, client


def test_upload_extract_and_facts_get():
    _, client = _started_client()
    r = client.post("/api/images", json={"image_b64": PNG_B64})
    assert r.status_code == 200
    body = r.json()
    assert len(body["image_id"]) == 64
    assert body["mime"] == "image/png"
    assert body["facts"]["status"] == "ok"

    r2 = client.get(f"/api/images/{body['image_id']}/facts")
    assert r2.status_code == 200
    assert r2.json()["facts"]["image_sha256"] == body["image_id"]


def test_upload_422_battery():
    _, client = _started_client()
    bad = [
        {"image_b64": ""},                                         # empty
        {"image_b64": base64.b64encode(b"not an image").decode()},  # bad magic
        {"image_b64": "!!!not-base64!!!"},                          # bad encoding
        {"image_b64": PNG_B64, "extra": 1},                        # extra=forbid
    ]
    for payload in bad:
        r = client.post("/api/images", json=payload)
        assert r.status_code == 422, payload


def test_attach_to_incident_and_404s():
    _, client = _started_client()
    img = client.post("/api/images", json={"image_b64": PNG_B64}).json()
    inc = client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "minor"},
    ).json()
    incident_id = inc["incident_id"]

    r = client.post(f"/api/incidents/{incident_id}/images",
                    json={"image_id": img["image_id"]})
    assert r.status_code == 200
    assert r.json()["vision"]["facts"]["scene"]
    got = client.get(f"/api/incidents/{incident_id}").json()
    assert got["incident"]["vision"]["image_id"] == img["image_id"]

    # 404s
    assert client.get("/api/images/" + "0" * 64 + "/facts").status_code == 404
    assert client.post("/api/incidents/inc-nope/images",
                       json={"image_id": img["image_id"]}).status_code == 404
    assert client.post(f"/api/incidents/{incident_id}/images",
                       json={"image_id": "0" * 64}).status_code == 404


def test_vision_mode_switch_mirrors_laya_mode():
    _, client = _started_client()
    r = client.post("/api/vision/mode", json={"mode": "cache"})
    assert r.status_code == 200
    assert r.json() == {"previous_mode": "mock", "mode": "cache"}
    assert client.post("/api/vision/mode", json={"mode": "quantum"}).status_code == 422
    assert client.post("/api/vision/mode",
                       json={"mode": "live", "extra": 1}).status_code == 422
