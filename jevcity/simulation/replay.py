"""Historical replay engine (plan Phase 1): streams recorded events through the
live pipeline with the original simulated timeline; speed scales wall-pacing only."""
from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from jevcity.schemas import EventEnvelope

DEFAULT_BASE = Path("datasets/jevcity")


def load_recording(path: str | Path, *, base: Path = DEFAULT_BASE) -> list[EventEnvelope]:
    """Load a JSONL recording of EventEnvelope rows. Rejects paths outside `base`."""
    target = Path(path)
    if not target.is_absolute() and target.parts[: len(base.parts)] != base.parts:
        target = base / target
    resolved = target.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise ValueError(f"recording must live under {base}, got {path}")
    try:
        lines = resolved.read_text().splitlines()
    except OSError as exc:
        raise ValueError(f"recording not readable: {path}") from exc
    events: list[EventEnvelope] = []
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(EventEnvelope.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"{path}:{lineno}: invalid event row ({exc.error_count()} errors)") from exc
    return events


def stream(
    sim,
    records: list[EventEnvelope],
    *,
    speed: float = 1.0,
    sleeper: Callable[[float], None] | None = None,
) -> int:
    """Append records in order; clock follows the recording's own deltas (speed-independent).
    `sleeper` receives wall pacing per gap (gap/speed); defaults to `time.sleep`.
    API sync path passes a no-op sleeper."""
    from jevcity.simulation.state import SimulationState

    if not isinstance(sim, SimulationState):
        raise TypeError("sim must be a SimulationState")
    if speed <= 0:
        raise ValueError(f"speed must be > 0, got {speed}")
    pace = sleeper if sleeper is not None else time.sleep
    previous = None
    for record in records:
        delta = (record.simulated_time - sim.clock.now).total_seconds()
        if delta > 0:
            sim.clock.advance(int(delta))
        if previous is not None:
            gap = (record.simulated_time - previous.simulated_time).total_seconds()
            if gap > 0:
                pace(gap / speed)
        sim.append_replay(record)
        previous = record
    return len(records)
