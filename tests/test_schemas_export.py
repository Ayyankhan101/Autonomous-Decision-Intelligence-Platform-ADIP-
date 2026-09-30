"""Frozen dashboard contracts: schemas/*.json must match the exporter byte-for-byte."""
from __future__ import annotations

from pathlib import Path

from jevcity.schemas.export import MODELS, export

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMITTED = REPO_ROOT / "schemas"


def test_schema_exports_are_fresh(tmp_path):
    written = export(tmp_path)
    assert len(written) == len(MODELS)
    for path in written:
        other = COMMITTED / path.name
        assert other.exists(), f"missing committed export: {other.name}"
        assert path.read_bytes() == other.read_bytes(), (
            f"{path.name} stale — run: uv run python -m jevcity.schemas.export"
        )


def test_no_untracked_schema_files():
    committed = {p.name for p in COMMITTED.glob("*.json")}
    expected = {f"{slug}.json" for slug in MODELS}
    assert committed == expected, (
        "schemas/ drift — run: uv run python -m jevcity.schemas.export"
    )
