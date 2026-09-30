"""Audit export (plan Phase 4: simple viewer/export): JSONL dump of the append-only store.

Read-only — opens the sqlite file with mode=ro, never mutates it. Chain integrity is
checked with the same canonical hash the writer uses, so a tampered row is reported
before export.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from jevcity.schemas import AuditEntry

from .log import GENESIS, payload_hash


class AuditExportError(RuntimeError):
    pass


def export_entries(db_path: str | Path) -> list[AuditEntry]:
    path = str(db_path)
    if path == ":memory:":
        raise AuditExportError(
            "in-memory audit log has no file to export — pass a sqlite path"
        )
    if not Path(path).exists():
        raise AuditExportError(f"audit database not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT payload FROM audit_log ORDER BY rowid").fetchall()
    finally:
        conn.close()
    payloads = [r[0] for r in rows]
    _validate_chain(payloads)
    return [AuditEntry.model_validate_json(p) for p in payloads]


def _validate_chain(payloads: list[str]) -> None:
    prev = GENESIS
    for payload in payloads:
        data = json.loads(payload)
        entry_id = data.get("entry_id", "?")
        entry_hash = data.pop("entry_hash", None)
        if data.get("previous_hash") != prev:
            raise AuditExportError(
                f"hash chain broken at {entry_id}: previous_hash mismatch"
            )
        if payload_hash(payload) != entry_hash:
            raise AuditExportError(
                f"hash chain broken at {entry_id}: entry_hash mismatch"
            )
        prev = entry_hash


def export_jsonl(db_path: str | Path) -> str:
    entries = export_entries(db_path)
    return "".join(e.model_dump_json() + "\n" for e in entries)
