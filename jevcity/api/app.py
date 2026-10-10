"""JevCity Command Center API (plan §5 endpoint list). Port 8200 — triage app owns 8100.

Run: uvicorn jevcity.api.app:app --port 8200
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from jevcity.audit.log import AuditLog
from jevcity.decision_engine.engine import JevCityEngine
from jevcity.decision_engine.laya_adapter.adapter import LayaAdapter
from jevcity.decision_engine.policy_position import weights_for
from jevcity.ingestion.trust import TrustRegistry
from jevcity.schemas import (
    AuditListResponse,
    AuditVerifyResponse,
    DecisionListResponse,
    DecisionRecord,
    IncidentListResponse,
    IncidentResponse,
    ImpactPreviewRequest,
    ImpactPreviewResponse,
    LayaMode,
    LayaModeRequest,
    LayaModeResponse,
    OverrideRecord,
    OverrideRequest,
    PolicyPositionRequest,
    PolicyPositionResponse,
    ResourceListResponse,
    SecondEmergencyRequest,
    SimulationActionResponse,
    SimulationBadDataRequest,
    SimulationIncidentRequest,
    SimulationResetRequest,
    SimulationStartRequest,
    StatePayload,
    SybilFloodRequest,
    SybilFloodResponse,
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
            policy_position=engine.policy_position,
            objective_weights=weights_for(engine.policy_position),
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
    def list_audit(
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    ) -> AuditListResponse:
        return AuditListResponse(entries=engine.audit.entries(limit=limit))

    # --- simulation controls -------------------------------------------

    @app.post("/api/simulation/start", response_model=SimulationActionResponse)
    def sim_start(req: SimulationStartRequest) -> SimulationActionResponse:
        records = None
        if req.recording is not None:
            try:
                records = load_recording(req.recording)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        engine.simulation.start(req.session_seed, req.scenario_seed)
        engine.adapter = LayaAdapter(mode=engine.adapter.mode)
        engine.decisions.clear()
        engine.decision_history.clear()
        engine.validation_by_event.clear()
        engine._processed = 0
        if records is None:
            return SimulationActionResponse()
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

    @app.post("/api/simulation/resume", response_model=SimulationActionResponse)
    def sim_resume() -> SimulationActionResponse:
        """Continue the current session without reseeding or clearing state
        (start() resets; this does not — fixes pause/resume data loss)."""
        engine.simulation.resume()
        return SimulationActionResponse()

    @app.post("/api/simulation/reset", response_model=SimulationActionResponse)
    def sim_reset(req: SimulationResetRequest) -> SimulationActionResponse:
        engine.simulation.reset(SeedConfig(req.session_seed, req.scenario_seed))
        engine.adapter = LayaAdapter(mode=engine.adapter.mode)
        engine.trust = TrustRegistry()
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
        try:
            incident_id = engine.simulation.inject_bad_data(req.mode, req.target_incident_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc
        records = engine.process_pending()
        return SimulationActionResponse(
            incident_id=incident_id, decision_ids=[r.decision_id for r in records]
        )

    @app.post("/api/simulation/sybil", response_model=SybilFloodResponse)
    def sim_sybil(req: SybilFloodRequest) -> SybilFloodResponse:
        incident_id, fake_sources = engine.simulation.inject_sybil(
            req.incident_type,
            req.zone,
            req.severity,
            reports=req.reports,
        )
        records = engine.process_pending()
        return SybilFloodResponse(
            incident_id=incident_id,
            fake_sources=fake_sources,
            decision_ids=[r.decision_id for r in records],
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
            raise HTTPException(404, str(exc).strip("'\"")) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        assert record.override is not None
        return record.override

    @app.post(
        "/api/overrides/impact", response_model=ImpactPreviewResponse
    )
    def override_impact(req: ImpactPreviewRequest) -> ImpactPreviewResponse:
        """Additive endpoint (enhancement 4): dry risk preview; never mutates state."""
        try:
            assessment = engine.assess_override(
                req.decision_id, req.override_type, req.new_priority
            )
        except KeyError as exc:
            raise HTTPException(404, str(exc).strip("'\"")) from exc
        return ImpactPreviewResponse(
            decision_id=req.decision_id,
            tier=assessment.tier,
            warning=assessment.warning,
            requires_ack=assessment.requires_ack,
            requires_context_code=assessment.requires_context_code,
            requires_break_glass=assessment.requires_break_glass,
            projected=assessment.projected,
        )

    # --- policy sandbox (enhancement 2, additive route) ----------------

    @app.post("/api/policy/position", response_model=PolicyPositionResponse)
    def policy_position_switch(req: PolicyPositionRequest) -> PolicyPositionResponse:
        """Switch the runtime policy position; changes apply to new decisions only
        unless reoptimise_active=True re-runs open incidents."""
        report = engine.switch_policy(
            req.position, reoptimise_active=req.reoptimise_active
        )
        return PolicyPositionResponse(**report)

    # --- demo-liveness pack (additive routes) --------------------------

    @app.get("/api/audit/verify", response_model=AuditVerifyResponse)
    def audit_verify() -> AuditVerifyResponse:
        """Recompute the full SHA-256 hash chain now; never mutates state."""
        report = engine.audit.chain_report()
        return AuditVerifyResponse(**report)

    @app.post("/api/simulation/laya-mode", response_model=LayaModeResponse)
    def laya_mode_switch(req: LayaModeRequest) -> LayaModeResponse:
        """Hot-swap the Laya adapter (mock|cache|live). Live loads lazily on the
        first decision; fail-closed routing handles load errors."""
        previous = engine.adapter.mode
        if req.mode != previous:
            engine.adapter = LayaAdapter(mode=req.mode)
        return LayaModeResponse(previous_mode=previous, mode=req.mode)

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
