"""Audit persistence: build_engine durable-by-default, env override, chain survives restart.

Builds on tests/test_audit.py (raw AuditLog basics) — this file covers the
build_engine resolution seam + restart-survival invariant."""
from __future__ import annotations

from pathlib import Path

from jevcity.api.app import build_engine
from jevcity.audit.log import AuditLog


def test_default_audit_path_is_durable(monkeypatch, tmp_path):
    monkeypatch.delenv("JEVCITY_AUDIT_PATH", raising=False)
    monkeypatch.chdir(tmp_path)  # keep the repo clean; path is repo-relative
    eng = build_engine()
    try:
        assert str(eng.audit.path) == "jevcity/audit/audit.db"
    finally:
        eng.audit.close()


def test_env_selects_audit_path(monkeypatch, tmp_path):
    target = tmp_path / "env.db"
    monkeypatch.setenv("JEVCITY_AUDIT_PATH", str(target))
    eng = build_engine()
    try:
        assert Path(eng.audit.path) == target
    finally:
        eng.audit.close()


def test_chain_survives_reopen(tmp_path):
    db = tmp_path / "chain.db"
    eng = build_engine(audit_path=str(db))
    eng.audit.append(actor="test", action="SIM_START", reason="warm")
    first = eng.audit.entries(limit=1)[0]
    eng.audit.close()

    reopened = AuditLog(db)
    assert reopened.chain_report() == {"ok": True, "entry_count": 1, "broken_at": None}
    nxt = reopened.append(actor="test", action="SIM_PAUSE", reason="pause")
    closed = nxt.entry_id.split("-")[1]
    assert int(closed) > int(first.entry_id.split("-")[1])  # numbering continues
    assert reopened.validate_chain() is True
    reopened.close()
