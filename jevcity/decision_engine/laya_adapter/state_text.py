"""Deterministic state -> text rendering for laya predict (Phase 2 eval, Phase 3 live)."""
from __future__ import annotations

import json

from jevcity.schemas import LayaState


def render_state(state: LayaState) -> str:
    payload = state.model_dump(mode="json")
    lines = [
        f"{key}={json.dumps(value, sort_keys=True, ensure_ascii=True)}"
        for key, value in sorted(payload.items())
    ]
    return "\n".join(lines)
