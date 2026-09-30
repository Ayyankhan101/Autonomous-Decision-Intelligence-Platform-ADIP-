"""Phase 4 audit export (tools/export_audit.py CLI backed by jevcity/audit/export.py)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from jevcity.audit.export import AuditExportError, export_entries, export_jsonl
from jevcity.audit.log import AuditLog
from jevcity.schemas import AuditLayaMetadata, LayaStatus


def _populated(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    log.append(actor="system", action="DECISION_EMITTED", reason="first")
    log.append(
        actor="op-1",
        action="OVERRIDE_APPLIED",
        reason="operator took control",
        decision_id="dec-000001",
        laya=AuditLayaMetadata(
            laya_status=LayaStatus.OK,
            laya_state_hash="sha256:aa",
            laya_questions_version="q-0.1.0",
            laya_fallback_used=False,
            laya_guardrail_modified=True,
        ),
    )
    return log


def test_export_round_trip_and_order(tmp_path):
    log = _populated(tmp_path)
    path = log.path
    log.close()
    entries = export_entries(path)
    assert [e.action for e in entries] == ["DECISION_EMITTED", "OVERRIDE_APPLIED"]
    assert entries[1].laya.laya_questions_version == "q-0.1.0"
    assert entries[1].laya.laya_guardrail_modified is True
    lines = export_jsonl(path).splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["actor"] == "op-1"


def test_export_refuses_memory_and_missing(tmp_path):
    with pytest.raises(AuditExportError, match="in-memory"):
        export_entries(":memory:")
    with pytest.raises(AuditExportError, match="not found"):
        export_entries(tmp_path / "nope.db")


def test_export_detects_tamper(tmp_path):
    log = _populated(tmp_path)
    path = log.path
    log.close()
    conn = sqlite3.connect(path)
    conn.executescript("DROP TRIGGER audit_no_update;")
    row = conn.execute(
        "SELECT payload FROM audit_log WHERE entry_id = 'aud-000002'"
    ).fetchone()
    tampered = json.loads(row[0])
    tampered["reason"] = "operator took control BUT EDITED"
    conn.execute(
        "UPDATE audit_log SET payload = ? WHERE entry_id = 'aud-000002'",
        (json.dumps(tampered),),
    )
    conn.commit()
    conn.close()
    with pytest.raises(AuditExportError, match="hash chain broken"):
        export_entries(path)
