# Phase 1 Replay Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two remaining plan-Phase-1 gaps (historical replay engine + dataset; Laya cache clearing on reset) and close Phase-0 exit item 1.

**Architecture:** Replay loads a checked-in JSONL recording of `EventEnvelope` rows, appends them to the simulation feed through the same path live injection uses, and runs the existing `process_pending()` pipeline. Speed scales only wall-pacing via an injectable sleeper — the simulated timeline always follows the recording's original `simulated_time` deltas, so decisions are speed-independent. The API exposes replay as two optional fields on the existing `POST /api/simulation/start` (endpoint list stays frozen at 16).

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, pytest, ruff.

## Global Constraints

- Frozen contracts: `jevcity/schemas/*.py` — additive changes only; re-run `uv run python -m jevcity.schemas.export` after any schema change.
- Endpoint list frozen at 16 (plan §5, sign-off item 10): no new endpoints; extend `SimulationStartRequest` only.
- Never host wall-clock in features/decisions — only `SimClock` (Invariants / plan Phase 1).
- `extra="forbid"` on API request models — new fields must be optional with defaults (backwards compatible).
- Laya decisions: deterministic policy decides (Errata); replay must not bypass guardrails.
- Style: no inline code comments; docstrings allowed (repo convention). ruff select = `E9,F`, line-length 100.
- Verification per task: `uv run ruff check .` and `uv run pytest -q` (baseline: 117 passed, 1 deselected).

---

### Task 1: Replay engine + recording dataset + API wiring

**Files:**
- Create: `jevcity/simulation/replay.py`
- Modify: `jevcity/simulation/state.py` (add `append_replay` method after `second_emergency`)
- Modify: `jevcity/schemas/api.py:73-77` (`SimulationStartRequest`)
- Modify: `jevcity/api/app.py:130-136` (`sim_start`)
- Create: `datasets/jevcity/sim-session-v1.jsonl` (generated, step 6)
- Modify: `docs/jevcity/API.md` (simulation controls table, `/start` row)
- Test: `tests/jevcity/test_replay.py`

**Interfaces:**
- Consumes: `SimulationState` (`.clock`, `.raw_events`, `.events`, `._register_incident`), `SimClock.advance(seconds)`, `EventEnvelope.model_validate_json`, `JevCityEngine.process_pending() -> list[DecisionRecord]`, `SimulationActionResponse(ok, incident_id, decision_ids)`.
- Produces: `load_recording(path: str | Path, *, base: Path = Path("datasets/jevcity")) -> list[EventEnvelope]`; `stream(sim: SimulationState, records: list[EventEnvelope], *, speed: float = 1.0, sleeper: Callable[[float], None] | None = None) -> int`; `SimulationState.append_replay(event: EventEnvelope) -> None`; `SimulationStartRequest.recording: str | None`, `.speed: float`.

- [ ] **Step 1: Write failing tests**

```python
# tests/jevcity/test_replay.py
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jevcity.api.app import build_engine, create_app
from jevcity.simulation.replay import load_recording, stream
from jevcity.simulation.seeds import SeedConfig
from jevcity.simulation.state import SimulationState

RECORDING = Path("datasets/jevcity/sim-session-v1.jsonl")


def test_load_recording_valid():
    events = load_recording(RECORDING)
    assert len(events) >= 8
    assert events == sorted(events, key=lambda e: e.simulated_time)
    assert len({e.event_id for e in events}) == len(events)


def test_load_rejects_path_escape(tmp_path):
    with pytest.raises(ValueError, match="datasets/jevcity"):
        load_recording("../../etc/passwd")


def test_load_rejects_invalid_row(tmp_path):
    bad = tmp_path / "bad.jsonl"
    good = RECORDING.read_text().splitlines()[0]
    bad.write_text(good + "\n" + '{"event_id": "broken"}\n')
    with pytest.raises(ValueError, match=":2:"):
        load_recording(bad, base=tmp_path)


def _replay_decisions(speed: float):
    engine = build_engine()
    engine.simulation.start(42, 7)
    records = load_recording(RECORDING)
    stream(engine.simulation, records, speed=speed, sleeper=lambda _s: None)
    out = engine.process_pending()
    return [(r.incident_id, r.state, r.priority) for r in out]


def test_replay_deterministic_across_speeds():
    assert _replay_decisions(1.0) == _replay_decisions(25.0)
    assert len(_replay_decisions(1.0)) >= 6


def test_replay_pacing_scales_with_speed():
    engine = build_engine()
    engine.simulation.start(42, 7)
    records = load_recording(RECORDING)
    slept: list[float] = []
    stream(engine.simulation, records, speed=2.0, sleeper=slept.append)
    gaps = [
        (b.simulated_time - a.simulated_time).total_seconds()
        for a, b in zip(records, records[1:])
    ]
    assert slept == [g / 2.0 for g in gaps if g > 0]


def test_replay_clock_follows_recording_timeline():
    engine = build_engine()
    engine.simulation.start(42, 7)
    records = load_recording(RECORDING)
    stream(engine.simulation, records, speed=7.5, sleeper=lambda _s: None)
    assert engine.simulation.simulated_time == records[-1].simulated_time


def test_api_start_with_recording():
    client = TestClient(create_app())
    r = client.post(
        "/api/simulation/start",
        json={"session_seed": 42, "scenario_seed": 7,
              "recording": "sim-session-v1.jsonl", "speed": 5.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["decision_ids"]) >= 6
    state = client.get("/api/state").json()
    assert state["incident_count"] >= 6


def test_api_start_bad_recording_422():
    client = TestClient(create_app())
    r = client.post(
        "/api/simulation/start",
        json={"session_seed": 42, "scenario_seed": 7, "recording": "../etc/passwd"},
    )
    assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/jevcity/test_replay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jevcity.simulation.replay'`

- [ ] **Step 3: Add `append_replay` to SimulationState**

Insert after `second_emergency` (state.py:121), before `# --- internals`:

```python
    def append_replay(self, event: EventEnvelope) -> None:
        """Register one pre-recorded event (plan Phase 1 replay path)."""
        self.raw_events.append(event.model_dump(mode="json"))
        self.events.append(event)
        self._register_incident(event)
```

- [ ] **Step 4: Implement `jevcity/simulation/replay.py`**

```python
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
    if not target.is_absolute():
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
    `sleeper` receives wall pacing per gap (gap/speed); None disables pacing (API sync path)."""
    from jevcity.simulation.state import SimulationState

    if not isinstance(sim, SimulationState):
        raise TypeError("sim must be a SimulationState")
    if speed <= 0:
        raise ValueError(f"speed must be > 0, got {speed}")
    pace = sleeper if sleeper is not None else (lambda _s: None)
    previous = None
    for record in records:
        if previous is not None:
            gap = (record.simulated_time - previous.simulated_time).total_seconds()
            if gap > 0:
                sim.clock.advance(int(gap))
                pace(gap / speed)
        sim.append_replay(record)
        previous = record
    return len(records)
```

- [ ] **Step 5: Extend `SimulationStartRequest` + `sim_start`**

`schemas/api.py` — replace lines 73-77:

```python
class SimulationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_seed: int = 42
    scenario_seed: int = 7
    recording: str | None = Field(
        default=None,
        description="JSONL recording filename under datasets/jevcity/ (replay mode)",
    )
    speed: float = Field(default=1.0, gt=0, le=100, description="wall pacing multiplier")
```

`api/app.py` — replace `sim_start` body; add import `from jevcity.simulation.replay import load_recording, stream`:

```python
    @app.post("/api/simulation/start", response_model=SimulationActionResponse)
    def sim_start(req: SimulationStartRequest) -> SimulationActionResponse:
        engine.simulation.start(req.session_seed, req.scenario_seed)
        engine.adapter = LayaAdapter(mode=engine.adapter.mode)
        if req.recording is None:
            return SimulationActionResponse()
        try:
            records = load_recording(req.recording)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        stream(engine.simulation, records, speed=req.speed, sleeper=lambda _s: None)
        out = engine.process_pending()
        return SimulationActionResponse(
            incident_id=records[0].incident_id if records else None,
            decision_ids=[r.decision_id for r in out],
        )
```

- [ ] **Step 6: Generate the recording**

Run from repo root:

```bash
uv run python - <<'EOF'
from pathlib import Path
from jevcity.schemas import IncidentType, SeverityHint, Zone
from jevcity.simulation.seeds import SeedConfig
from jevcity.simulation.state import SimulationState

sim = SimulationState(SeedConfig(42, 7))
sim.start(42, 7)
plan = [
    (IncidentType.ACCIDENT, Zone.NORTH, SeverityHint.SEVERE, True),
    (IncidentType.FIRE, Zone.SOUTH, SeverityHint.MODERATE, False),
    (IncidentType.FLOOD, Zone.EAST, None, True),
    (IncidentType.MEDICAL, Zone.WEST, SeverityHint.MINOR, False),
    (IncidentType.ACCIDENT, Zone.CENTRAL, None, False),
    (IncidentType.FIRE, Zone.EAST, SeverityHint.SEVERE, True),
    (IncidentType.MEDICAL, Zone.NORTH, None, False),
    (IncidentType.FLOOD, Zone.WEST, SeverityHint.MODERATE, False),
]
for incident_type, zone, severity, multi in plan:
    sim.inject_incident(incident_type, zone, severity, multi_report=multi)
out = Path("datasets/jevcity/sim-session-v1.jsonl")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("".join(e.model_dump_json() + "\n" for e in sim.events))
print(len(sim.events), "rows ->", out)
EOF
```

Expected: ≥ 16 rows (8 incidents + multi-report companions). Verify: `head -1 datasets/jevcity/sim-session-v1.jsonl | uv run python -c "import sys,json; json.loads(sys.stdin.read()); print('ok')"`

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/jevcity/test_replay.py -v`
Expected: 7 passed. If `test_replay_pacing_scales_with_speed` fails, check gap sign (recordings are time-ordered; generation guarantees it).

- [ ] **Step 8: Re-export schemas + docs**

Run: `uv run python -m jevcity.schemas.export`

Modify `docs/jevcity/API.md` simulation-controls table row:

```markdown
| POST | `/api/simulation/start` | `{session_seed, scenario_seed, recording?, speed?}` — `recording` = JSONL filename under `datasets/jevcity/` streams the recording through the live pipeline (sync; `speed` reserved for live pacing) |
```

- [ ] **Step 9: Full verify**

Run: `uv run ruff check . && uv run pytest -q`
Expected: All checks passed! · 124 passed, 1 deselected (117 + 7 new)

- [ ] **Step 10: Commit**

```bash
git add jevcity/simulation/replay.py jevcity/simulation/state.py jevcity/schemas/api.py \
  jevcity/api/app.py datasets/jevcity/ tests/jevcity/test_replay.py schemas/ docs/jevcity/API.md
git commit -m "Add Phase 1 replay engine: JSONL recording stream, seed 42/7 dataset, start-endpoint wiring"
```

---

### Task 2: Reset clears Laya adapter cache

**Files:**
- Modify: `jevcity/api/app.py:141-148` (`sim_reset`)
- Test: `tests/jevcity/test_api.py` (append test)

**Interfaces:**
- Consumes: existing `sim_start` pattern `engine.adapter = LayaAdapter(mode=engine.adapter.mode)`.
- Produces: after `POST /api/simulation/reset`, `engine.adapter.cache == {}` in cache mode.

- [ ] **Step 1: Write failing test** (append to `tests/jevcity/test_api.py`)

```python
def test_reset_clears_laya_cache():
    engine = build_engine(mode=LayaMode.CACHE)
    client = TestClient(create_app(engine))
    client.post("/api/simulation/start", json={"session_seed": 42, "scenario_seed": 7})
    client.post(
        "/api/simulation/incident",
        json={"incident_type": "accident", "zone": "north", "severity": "severe"},
    )
    assert engine.adapter.cache  # populated by the incident decision
    client.post(
        "/api/simulation/reset",
        json={"session_seed": 42, "scenario_seed": 7},
    )
    assert engine.adapter.cache == {}
```

Check imports at top of `test_api.py`: `LayaMode` needs adding to the `jevcity.schemas` import (existing import already has `build_engine`, `create_app`, `TestClient`).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/jevcity/test_api.py::test_reset_clears_laya_cache -v`
Expected: FAIL — `assert engine.adapter.cache == {}` (cache retained)

- [ ] **Step 3: Fix `sim_reset`**

```python
    @app.post("/api/simulation/reset", response_model=SimulationActionResponse)
    def sim_reset(req: SimulationResetRequest) -> SimulationActionResponse:
        engine.simulation.reset(SeedConfig(req.session_seed, req.scenario_seed))
        engine.adapter = LayaAdapter(mode=engine.adapter.mode)
        engine.decisions.clear()
        engine.decision_history.clear()
        engine.validation_by_event.clear()
        engine._processed = 0
        return SimulationActionResponse()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/jevcity/test_api.py -q`
Expected: all API tests pass (16 passed + new)

- [ ] **Step 5: Commit**

```bash
git add jevcity/api/app.py tests/jevcity/test_api.py
git commit -m "Clear Laya adapter cache on simulation reset (plan Phase 1 cache-clearing bullet)"
```

---

### Task 3: Close Phase-0 exit item 1

**Files:**
- Modify: `docs/jevcity/PHASE0_SIGNOFF.md:14` (item 1 row), `:51-52` (Gate 1 verdict)

**Interfaces:**
- Consumes: Task 1 artifacts (`datasets/jevcity/sim-session-v1.jsonl`, `jevcity/simulation/replay.py`).
- Produces: updated Gate 1 status.

- [ ] **Step 1: Update item 1 row**

```markdown
| 1 | Dataset feasibility check complete | ✅ | Chosen: synthetic simulator = primary source (deterministic, seeded); replay recordings under `datasets/jevcity/` (`sim-session-v1.jsonl`, generated by `jevcity/simulation/state.py` seeds 42/7) = secondary; no external historical dataset needed |
```

- [ ] **Step 2: Update Gate 1 verdict**

```markdown
**Gate 1 verdict:** 🟡 not closable — items 12, 18, 21 open (live Laya integration +
fixture/calibration class = Phase 2/3-bound; none block the Phase 1→2 build under the
mock adapter).
```

- [ ] **Step 3: Verify doc links still resolve**

Run: `grep -c "datasets/jevcity" docs/jevcity/PHASE0_SIGNOFF.md` → ≥ 1

- [ ] **Step 4: Commit**

```bash
git add docs/jevcity/PHASE0_SIGNOFF.md
git commit -m "Close Phase-0 exit item 1: dataset choice (synthetic primary + replay recordings)"
```

---

## Self-review record

- Spec coverage: all 16 plan-Phase-1 bullets now ✅ or N/A (14 ✅ built, replay=Task 1, cache-clear=Task 2, non-English=N/A in DEMO_BEATS); Phase-0 item 1 → Task 3.
- Placeholders: none — every step carries concrete code.
- Type consistency: `load_recording`, `stream`, `append_replay`, `recording`, `speed` used identically across tasks.
