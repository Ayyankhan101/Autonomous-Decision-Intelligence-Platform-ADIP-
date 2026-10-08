"""JevCity Command Center API (plan §5 endpoint list). Port 8200 — triage app owns 8100.

Run: uvicorn jevcity.api.app:app --port 8200
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from jevcity.audit.log import AuditLog
from jevcity.decision_engine.engine import JevCityEngine
from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
from jevcity.schemas import (
    AuditListResponse,
    DecisionListResponse,
    DecisionRecord,
    IncidentListResponse,
    IncidentResponse,
    LayaMode,
    OverrideRecord,
    OverrideRequest,
    ResourceListResponse,
    SecondEmergencyRequest,
    SimulationActionResponse,
    SimulationBadDataRequest,
    SimulationIncidentRequest,
    SimulationResetRequest,
    SimulationStartRequest,
    StatePayload,
    WhatIfRequest,
    WhatIfResult,
)
from jevcity.simulation.replay import load_recording, stream
from jevcity.simulation.seeds import SeedConfig
from jevcity.simulation.state import SimulationState


def build_engine(
    *,
    mode: LayaMode = LayaMode.MOCK,
    audit_path: str = ":memory:",
    session_seed: int = 42,
    scenario_seed: int = 7,
) -> JevCityEngine:
    simulation = SimulationState(SeedConfig(session_seed, scenario_seed))
    return JevCityEngine(
        simulation,
        adapter=LayaAdapter(mode=mode),
        audit=AuditLog(audit_path),
    )


def create_app(engine: JevCityEngine | None = None) -> FastAPI:
    engine = engine or build_engine()
    app = FastAPI(title="JevCity Command Center API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    sandbox_store: dict[str, WhatIfResult] = {}

    def _decisions_for(incident_id: str) -> list[DecisionRecord]:
        return [d for d in engine.decision_history if d.incident_id == incident_id]

    # --- read endpoints -------------------------------------------------

    @app.get("/api/state", response_model=StatePayload)
    def get_state() -> StatePayload:
        sim = engine.simulation
        return StatePayload(
            simulated_time=sim.simulated_time,
            running=sim.running,
            session_seed=sim.config.session_seed,
            scenario_seed=sim.config.scenario_seed,
            incident_count=len(sim.incidents),
            decision_count=len(engine.decisions),
            open_incident_count=sum(
                1
                for i in sim.incidents.values()
                if i.lifecycle.value not in ("resolved",)
            ),
            available_resources=sim.pool.counts_available_by_type(),
            laya_mode=engine.adapter.mode.value,
            last_laya_status=(
                engine.decision_history[-1].laya.status.value
                if engine.decision_history and engine.decision_history[-1].laya
                else None
            ),
        )

    @app.get("/api/incidents", response_model=IncidentListResponse)
    def list_incidents() -> IncidentListResponse:
        return IncidentListResponse(incidents=list(engine.simulation.incidents.values()))

    @app.get("/api/incidents/{incident_id}", response_model=IncidentResponse)
    def get_incident(incident_id: str) -> IncidentResponse:
        incident = engine.simulation.incidents.get(incident_id)
        if incident is None:
            raise HTTPException(404, f"unknown incident {incident_id}")
        history = _decisions_for(incident_id)
        validation = next(
            (
                v
                for v in engine.validation_by_event.values()
                if v.incident_id == incident_id
            ),
            None,
        )
        return IncidentResponse(
            incident=incident,
            validation=validation,
            latest_decision=history[-1] if history else None,
        )

    @app.get("/api/decisions", response_model=DecisionListResponse)
    def list_decisions() -> DecisionListResponse:
        return DecisionListResponse(decisions=list(engine.decision_history))

    @app.get("/api/decisions/{decision_id}", response_model=DecisionRecord)
    def get_decision(decision_id: str) -> DecisionRecord:
        record = engine.decisions.get(decision_id)
        if record is None:
            raise HTTPException(404, f"unknown decision {decision_id}")
        return record

    @app.get("/api/resources", response_model=ResourceListResponse)
    def list_resources() -> ResourceListResponse:
        return ResourceListResponse(resources=engine.simulation.pool.all())

    @app.get("/api/audit", response_model=AuditListResponse)
    def list_audit(limit: int = 100) -> AuditListResponse:
        return AuditListResponse(entries=engine.audit.entries(limit=limit))

    # --- simulation controls -------------------------------------------

    @app.post("/api/simulation/start", response_model=SimulationActionResponse)
    def sim_start(req: SimulationStartRequest) -> SimulationActionResponse:
        engine.simulation.start(req.session_seed, req.scenario_seed)
        engine.adapter = LayaAdapter(mode=engine.adapter.mode)
        engine.decisions.clear()
        engine.decision_history.clear()
        engine.validation_by_event.clear()
        engine._processed = 0
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

    @app.post("/api/simulation/pause", response_model=SimulationActionResponse)
    def sim_pause() -> SimulationActionResponse:
        engine.simulation.pause()
        return SimulationActionResponse()

    @app.post("/api/simulation/reset", response_model=SimulationActionResponse)
    def sim_reset(req: SimulationResetRequest) -> SimulationActionResponse:
        engine.simulation.reset(SeedConfig(req.session_seed, req.scenario_seed))
        engine.adapter = LayaAdapter(mode=engine.adapter.mode)
        engine.decisions.clear()
        engine.decision_history.clear()
        engine.validation_by_event.clear()
        engine._processed = 0
        return SimulationActionResponse()

    @app.post("/api/simulation/incident", response_model=SimulationActionResponse)
    def sim_incident(req: SimulationIncidentRequest) -> SimulationActionResponse:
        incident_id = engine.simulation.inject_incident(
            req.incident_type,
            req.zone,
            req.severity,
            source_id=req.source_id,
            notes=req.notes,
            multi_report=req.multi_report,
        )
        records = engine.process_pending()
        return SimulationActionResponse(
            incident_id=incident_id, decision_ids=[r.decision_id for r in records]
        )

    @app.post("/api/simulation/bad-data", response_model=SimulationActionResponse)
    def sim_bad_data(req: SimulationBadDataRequest) -> SimulationActionResponse:
        incident_id = engine.simulation.inject_bad_data(req.mode, req.target_incident_id)
        records = engine.process_pending()
        return SimulationActionResponse(
            incident_id=incident_id, decision_ids=[r.decision_id for r in records]
        )

    @app.post("/api/simulation/second-emergency", response_model=SimulationActionResponse)
    def sim_second_emergency(req: SecondEmergencyRequest) -> SimulationActionResponse:
        incident_id = engine.simulation.second_emergency(req.incident_type, req.zone)
        records = engine.process_pending()
        return SimulationActionResponse(
            incident_id=incident_id, decision_ids=[r.decision_id for r in records]
        )

    # --- overrides (Invariant 7) ---------------------------------------

    @app.post("/api/overrides", response_model=OverrideRecord)
    def apply_override(req: OverrideRequest) -> OverrideRecord:
        try:
            record = engine.apply_override(req)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        assert record.override is not None
        return record.override

    # --- What-If (Invariants 6, 15) ------------------------------------

    @app.post("/api/what-if/run", response_model=WhatIfResult)
    def what_if_run(req: WhatIfRequest) -> WhatIfResult:
        try:
            result = engine.run_what_if(req)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
        sandbox_store[result.sandbox_id] = result
        return result

    @app.get("/api/what-if/{sandbox_id}/result", response_model=WhatIfResult)
    def what_if_result(sandbox_id: str) -> WhatIfResult:
        result = sandbox_store.get(sandbox_id)
        if result is None:
            raise HTTPException(404, f"unknown sandbox {sandbox_id}")
        return result

    dist_dir = Path(__file__).resolve().parents[2] / "dashboard" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="dashboard")

    app.state.engine = engine
    return app


app = create_app()
