#!/usr/bin/env python3
"""Validator for the ADIP golden set (ticket-triage v1).

Dependency-free: hand-checks every constraint the JSON Schema declares,
plus the composition targets from guidelines.md section 3 in --strict mode.

Usage:
  python3 datasets/golden-set/validate.py --file datasets/golden-set/golden-template.json
  python3 datasets/golden-set/validate.py --file datasets/golden-set/golden-template.json \
      --strict --expect 50

Exit 0 = valid, 1 = errors found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

LANGS = {"en", "es", "de", "fr", "zh", "other"}
SOURCES = {"handwritten", "public-dataset-derived", "synthetic"}
DEPTS = {"billing", "technical", "sales", "account"}

TICKET_ID_RE = re.compile(r"^TICKET-[0-9]{4}$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LONG_DIGITS_RE = re.compile(r"\d{7,}")
HANDLE_RE = re.compile(r"(?<![\w.])@(?!\w*\.\w)[A-Za-z0-9_]{3,}")
HARD_CASE_REF_RE = re.compile(r"\bH\d+\b")

# Exemplar labels are frozen; the validator flags accidental edits.
EXEMPLAR_LABELS = {
    "TICKET-0001": {"department": "billing", "urgency": 1, "refund": True},
    "TICKET-0002": {"department": "technical", "urgency": 0, "refund": False},
    "TICKET-0003": {"department": "sales", "urgency": 0, "refund": False},
    "TICKET-0004": {"department": "account", "urgency": 2, "refund": False},
    "TICKET-0005": {"department": "billing", "urgency": 0, "refund": False},
}

DEPT_TARGETS = {"billing": 15, "technical": 15, "sales": 8, "account": 12}
URGENCY_TARGETS = {0: 20, 1: 18, 2: 12}
REFUND_TRUE_TARGET = 15
NON_EN_TARGET = 6
HARD_CASE_MIN = 8

META_KEYS = {"labeler", "confident", "second_labeler", "disagreement",
             "hard_case", "notes", "source_url"}


def load_records(path: Path) -> list[dict]:
    obj = json.loads(path.read_text())
    if isinstance(obj, dict):
        return obj.get("records", [])
    if isinstance(obj, list):
        return obj
    raise SystemExit(f"{path}: top level must be an object with 'records' or a list")


def check_record(rec: dict, idx: int, errors: list[str]) -> None:
    where = f"record[{idx}]"

    if not isinstance(rec, dict):
        errors.append(f"{where}: not an object")
        return

    where = f"{where}({rec.get('ticket_id', '?')})"

    # --- required keys / no extras ---
    required = ["ticket_id", "text", "language", "source", "labels", "meta"]
    for key in required:
        if key not in rec:
            errors.append(f"{where}: missing required key '{key}'")
    extras = set(rec) - set(required)
    if extras:
        errors.append(f"{where}: unexpected keys {sorted(extras)}")
    if any(key not in rec for key in required):
        return  # cannot continue meaningfully

    # --- ticket_id ---
    tid = rec["ticket_id"]
    if not isinstance(tid, str) or not TICKET_ID_RE.match(tid):
        errors.append(f"{where}: ticket_id must match TICKET-#### , got {tid!r}")

    # --- text ---
    text = rec["text"]
    if not isinstance(text, str) or not (20 <= len(text) <= 2000):
        errors.append(f"{where}: text length {len(text) if isinstance(text, str) else '?'} outside 20..2000")
    else:
        if EMAIL_RE.search(text):
            errors.append(f"{where}: possible raw email in text (redact to [EMAIL])")
        if LONG_DIGITS_RE.search(text):
            errors.append(f"{where}: digit run >= 7 in text (possible phone/card; redact)")
        if HANDLE_RE.search(text):
            errors.append(f"{where}: possible @handle in text (redact or rephrase)")

    # --- language / source ---
    if rec["language"] not in LANGS:
        errors.append(f"{where}: language {rec['language']!r} not in {sorted(LANGS)}")
    if rec["source"] not in SOURCES:
        errors.append(f"{where}: source {rec['source']!r} not in {sorted(SOURCES)}")

    # --- labels ---
    labels = rec["labels"]
    if not isinstance(labels, dict):
        errors.append(f"{where}: labels must be an object")
        return
    if set(labels) != {"department", "urgency", "refund"}:
        errors.append(f"{where}: labels keys must be exactly department/urgency/refund, got {sorted(labels)}")
        return
    if labels["department"] not in DEPTS:
        errors.append(f"{where}: department {labels['department']!r} not in {sorted(DEPTS)}")
    u = labels["urgency"]
    if not isinstance(u, int) or isinstance(u, bool) or u not in (0, 1, 2):
        errors.append(f"{where}: urgency must be integer 0..2, got {u!r}")
    if not isinstance(labels["refund"], bool):
        errors.append(f"{where}: refund must be boolean, got {labels['refund']!r}")

    # --- exemplar protection ---
    if tid in EXEMPLAR_LABELS and labels != EXEMPLAR_LABELS[tid]:
        errors.append(f"{where}: exemplar labels were edited! expected {EXEMPLAR_LABELS[tid]}, got {labels}")

    # --- meta ---
    meta = rec["meta"]
    if not isinstance(meta, dict):
        errors.append(f"{where}: meta must be an object")
        return
    extras = set(meta) - META_KEYS
    if extras:
        errors.append(f"{where}: unexpected meta keys {sorted(extras)}")
    if not isinstance(meta.get("labeler"), str) or not meta.get("labeler", "").strip():
        errors.append(f"{where}: meta.labeler must be a non-empty string")
    if not isinstance(meta.get("confident"), bool):
        errors.append(f"{where}: meta.confident must be boolean")
    if meta.get("hard_case") is True:
        notes = meta.get("notes", "")
        if not HARD_CASE_REF_RE.search(notes):
            errors.append(f"{where}: hard_case=true but notes do not cite a hard-case id (H1..H10)")

    if rec["source"] == "public-dataset-derived" and not meta.get("source_url"):
        errors.append(f"{where}: public-dataset-derived requires meta.source_url")


def composition(records: list[dict], expect: int, errors: list[str],
                warnings: list[str]) -> None:
    n = len(records)
    if n != expect:
        errors.append(f"composition: {n} records, expected {expect}")

    depts = Counter(r.get("labels", {}).get("department") for r in records)
    urg = Counter(r.get("labels", {}).get("urgency") for r in records)
    refund_true = sum(1 for r in records if r.get("labels", {}).get("refund") is True)
    non_en = sum(1 for r in records if r.get("language") not in (None, "en"))
    hard = sum(1 for r in records if r.get("meta", {}).get("hard_case") is True)

    warnings.append(f"composition snapshot: departments={dict(depts)} urgencies={dict(urg)} "
                    f"refund_true={refund_true} non_en={non_en} hard_cases={hard}")

    if expect == 50:
        for d, target in DEPT_TARGETS.items():
            if depts.get(d, 0) != target:
                errors.append(f"composition: department {d} = {depts.get(d, 0)}, target {target}")
        for u, target in URGENCY_TARGETS.items():
            if urg.get(u, 0) != target:
                errors.append(f"composition: urgency {u} = {urg.get(u, 0)}, target {target}")
        if refund_true != REFUND_TRUE_TARGET:
            errors.append(f"composition: refund=true = {refund_true}, target {REFUND_TRUE_TARGET}")
        if non_en != NON_EN_TARGET:
            errors.append(f"composition: non-en = {non_en}, target {NON_EN_TARGET}")
        if hard < HARD_CASE_MIN:
            errors.append(f"composition: hard cases = {hard}, minimum {HARD_CASE_MIN}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--strict", action="store_true",
                    help="also enforce composition targets (full 50-ticket freeze)")
    ap.add_argument("--expect", type=int, default=None,
                    help="expected record count (defaults: 50 in --strict, else no count check)")
    args = ap.parse_args()

    records = load_records(Path(args.file))
    errors: list[str] = []
    warnings: list[str] = []

    ids = [r.get("ticket_id") for r in records if isinstance(r, dict)]
    dupes = [t for t, c in Counter(ids).items() if c > 1]
    if dupes:
        errors.append(f"duplicate ticket_ids: {dupes}")

    for i, rec in enumerate(records):
        check_record(rec, i, errors)

    expect = args.expect if args.expect is not None else (50 if args.strict else len(records))
    composition(records, expect, errors if args.strict else [], warnings)

    for w in warnings:
        print(f"NOTE: {w}")
    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK: {len(records)} record(s) valid"
          + (" (structural only; use --strict for composition)" if not args.strict else " (strict)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
