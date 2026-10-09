"""Append-only audit log (plan §3.1.4, Phase 4).

Invariant 8 is enforced technically: SQLite triggers ABORT any UPDATE/DELETE, so the store
cannot be mutated even with direct SQL through this connection. Hash-linked entries
(previous_hash, entry_hash) make tampering detectable via validate_chain().
Invariant 15: dry_run entries are rejected — What-If never reaches the live audit.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jevcity.schemas import AuditEntry, AuditLayaMetadata

GENESIS = "sha256:genesis"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id     TEXT PRIMARY KEY,
    timestamp    TEXT NOT NULL,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT '',
    decision_id  TEXT,
    incident_id  TEXT,
    policy_version TEXT,
    dry_run      INTEGER NOT NULL DEFAULT 0,
    payload      TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    entry_hash   TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update
BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete
BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def _canonical(fields: dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash(payload: str) -> str:
    """Hash the stored payload bytes (minus entry_hash) — schema-stable across releases."""
    data = json.loads(payload)
    data.pop("entry_hash", None)
    return "sha256:" + hashlib.sha256(_canonical(data).encode()).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path = "jevcity/audit/audit.db") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._counter = self._load_counter()

    def _load_counter(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
        return int(row[0])

    @property
    def last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS

    def append(
        self,
        *,
        actor: str,
        action: str,
        reason: str = "",
        before_state: str | None = None,
        after_state: str | None = None,
        decision_id: str | None = None,
        incident_id: str | None = None,
        policy_version: str | None = None,
        model_versions: dict[str, str] | None = None,
        laya: AuditLayaMetadata | None = None,
        timestamp: datetime | None = None,
        dry_run: bool = False,
        cited_clause: str | None = None,
        reason_code: str | None = None,
        impact_tier: str | None = None,
        context_code: str | None = None,
        break_glass: bool = False,
    ) -> AuditEntry:
        if dry_run:
            raise ValueError("dry_run entries must never reach the live audit (Invariant 15)")
        self._counter += 1
        entry = AuditEntry(
            entry_id=f"aud-{self._counter:06d}",
            timestamp=timestamp or datetime.now(UTC),
            actor=actor,
            action=action,
            reason=reason,
            before_state=before_state,
            after_state=after_state,
            decision_id=decision_id,
            incident_id=incident_id,
            policy_version=policy_version,
            model_versions=model_versions or {},
            laya=laya or AuditLayaMetadata(),
            cited_clause=cited_clause,
            reason_code=reason_code,
            impact_tier=impact_tier,
            context_code=context_code,
            break_glass=break_glass,
            previous_hash=self.last_hash,
            entry_hash="sha256:pending",
        )
        if entry.dry_run:
            raise ValueError("dry_run entries must never reach the live audit (Invariant 15)")
        entry = entry.model_copy(
            update={"entry_hash": self._compute_hash(entry)}
        )
        self._conn.execute(
            """INSERT INTO audit_log
               (entry_id, timestamp, actor, action, reason, decision_id, incident_id,
                policy_version, dry_run, payload, previous_hash, entry_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.entry_id, entry.timestamp.isoformat(), entry.actor, entry.action,
                entry.reason, entry.decision_id, entry.incident_id, entry.policy_version,
                int(entry.dry_run), entry.model_dump_json(), entry.previous_hash,
                entry.entry_hash,
            ),
        )
        self._conn.commit()
        return entry

    @staticmethod
    def _compute_hash(entry: AuditEntry) -> str:
        fields = entry.model_dump(mode="json", exclude={"entry_hash"})
        return "sha256:" + hashlib.sha256(_canonical(fields).encode()).hexdigest()

    def entries(
        self, *, limit: int = 100, decision_id: str | None = None
    ) -> list[AuditEntry]:
        if decision_id:
            rows = self._conn.execute(
                "SELECT payload FROM audit_log WHERE decision_id = ? ORDER BY rowid DESC LIMIT ?",
                (decision_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT payload FROM audit_log ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [AuditEntry.model_validate_json(r[0]) for r in rows]

    def validate_chain(self) -> bool:
        rows = self._conn.execute(
            "SELECT payload FROM audit_log ORDER BY rowid"
        ).fetchall()
        prev = GENESIS
        for (payload,) in rows:
            data = json.loads(payload)
            entry_hash = data.pop("entry_hash", None)
            if data.get("previous_hash") != prev:
                return False
            if payload_hash(payload) != entry_hash:
                return False
            prev = entry_hash
        return True

    def chain_report(self) -> dict[str, int | bool | None]:
        """Full-chain recompute for the live dashboard verify button (demo-liveness).

        Returns {ok, entry_count, broken_at} — broken_at is the 1-based position of
        the first bad entry, None when intact.
        """
        rows = self._conn.execute(
            "SELECT payload FROM audit_log ORDER BY rowid"
        ).fetchall()
        prev = GENESIS
        for idx, (payload,) in enumerate(rows, start=1):
            try:
                data = json.loads(payload)
                entry_hash = data.pop("entry_hash", None)
                intact = (
                    data.get("previous_hash") == prev
                    and payload_hash(payload) == entry_hash
                )
            except (json.JSONDecodeError, AttributeError, TypeError):
                intact = False
            if not intact:
                return {"ok": False, "entry_count": len(rows), "broken_at": idx}
            prev = entry_hash
        return {"ok": True, "entry_count": len(rows), "broken_at": None}

    def close(self) -> None:
        self._conn.close()
