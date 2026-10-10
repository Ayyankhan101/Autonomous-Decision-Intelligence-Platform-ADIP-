from __future__ import annotations

import sqlite3

import pytest

from jevcity.audit.log import AuditLog, GENESIS


@pytest.fixture
def log(tmp_path):
    store = AuditLog(tmp_path / "audit.db")
    yield store
    store.close()


def test_entries_are_hash_linked(log):
    e1 = log.append(actor="system", action="DECISION_EMITTED", decision_id="dec-1")
    e2 = log.append(actor="system", action="DECISION_EMITTED", decision_id="dec-2")
    assert e1.previous_hash == GENESIS
    assert e2.previous_hash == e1.entry_hash
    assert log.validate_chain() is True


def test_update_blocked_by_trigger(log):
    log.append(actor="op", action="DECISION_EMITTED", decision_id="dec-1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        log._conn.execute("UPDATE audit_log SET reason='tampered'")
    assert log.entries(limit=1)[0].reason == ""


def test_delete_blocked_by_trigger(log):
    log.append(actor="op", action="DECISION_EMITTED", decision_id="dec-1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        log._conn.execute("DELETE FROM audit_log")
    assert len(log.entries(limit=10)) == 1


def test_chain_detects_payload_tamper(log):
    log.append(actor="system", action="DECISION_EMITTED", decision_id="dec-1")
    log.append(actor="system", action="DECISION_EMITTED", decision_id="dec-2")
    # DB-level attacker: drop protective trigger, corrupt payload, restore trigger
    log._conn.execute("DROP TRIGGER audit_no_update")
    log._conn.execute(
        "UPDATE audit_log SET payload = replace(payload, 'dec-2', 'dec-X') "
        "WHERE entry_id = 'aud-000002'"
    )
    log._conn.execute(
        "CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
    )
    log._conn.commit()
    assert log.validate_chain() is False  # hash chain catches what triggers block


def test_dry_run_entries_rejected(log):
    with pytest.raises(ValueError, match="Invariant 15"):
        log.append(actor="system", action="WHAT_IF", dry_run=True)


def test_override_entry_records_actor_and_reason(log):
    entry = log.append(
        actor="op-7",
        action="OVERRIDE_APPLIED",
        reason="field confirmation",
        before_state="HOLD_FOR_HUMAN",
        after_state="OVERRIDE_ACTIVE",
        decision_id="dec-1",
        policy_version="0.1.0",
    )
    assert entry.actor == "op-7"
    assert entry.reason == "field confirmation"
    assert entry.previous_hash == GENESIS
    assert log.validate_chain() is True


def test_concurrent_appends_keep_chain_intact(log):
    import threading

    failures: list[BaseException] = []

    def worker(tag: int) -> None:
        try:
            for i in range(25):
                log.append(
                    actor="system",
                    action="DECISION_EMITTED",
                    decision_id=f"dec-{tag}-{i}",
                )
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(tag,)) for tag in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not failures
    entries = log.entries(limit=1000)
    assert len(entries) == 100
    assert len({entry.entry_id for entry in entries}) == 100
    assert log.validate_chain() is True
