#!/usr/bin/env python3
"""Export the append-only audit log as JSONL (plan Phase 4 'audit log viewer/export').

Usage:
    uv run python tools/export_audit.py [--db PATH] [--out FILE]

Default db: jevcity/audit/audit.db (same default as the live store). Writes to
stdout unless --out is given. Exits non-zero on a missing db or broken hash chain.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from jevcity.audit.export import AuditExportError, export_jsonl  # noqa: E402

DEFAULT_DB = REPO_ROOT / "jevcity" / "audit" / "audit.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB), help="sqlite audit path")
    parser.add_argument("--out", default=None, help="output file (default: stdout)")
    args = parser.parse_args(argv)
    try:
        text = export_jsonl(args.db)
    except AuditExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
