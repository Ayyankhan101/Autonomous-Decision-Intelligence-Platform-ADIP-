"""Shared dataset loading for Phase 2 models: one JSONL, one split rule (i % 5 == 0 = held-out)."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_DATASET = Path("datasets/jevcity/ml/dataset.jsonl")


def load_dataset(path: Path = DEFAULT_DATASET) -> tuple[list[dict], list[dict]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"empty dataset: {path}")
    train = [row for i, row in enumerate(rows) if i % 5 != 0]
    held = [row for i, row in enumerate(rows) if i % 5 == 0]
    if not train or not held:
        raise ValueError(f"degenerate split in {path}")
    return train, held
