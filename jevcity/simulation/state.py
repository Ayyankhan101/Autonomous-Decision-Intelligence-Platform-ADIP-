"""Simulation aggregate: clock, seeded RNGs, raw event feed, incident/resource registries.
Owns the session seed story (plan Phase 1) and powers every simulation control endpoint."""
from __future__ import annotations

from datetime import datetime

from jevcity.schemas import (
    EventEnvelope,
    IncidentRecord,
    IncidentType,
    InjectionMode,
    SeverityHint,
    ValidationStatus,
    Zone,
)
from jevcity.schemas.resources import IncidentLifecycle

from .bad_data import apply_bad_data
from .clock import SimClock
from .event_gen import EventGenerator
from .resource_pool import ResourcePool
from .seeds import SeedConfig, build_rngs


class SimulationState:
    def __init__(self, config: SeedConfig | None = None) -> None:
        self.reset(config or SeedConfig())

    def reset(self, config: SeedConfig | None = None) -> None:
        self.config = config or self.config
        self.session_rng, self.scenario_rng = build_rngs(self.config)
        self.clock = SimClock()
        self.generator = EventGenerator(self.session_rng, self.scenario_rng)
        self.pool = ResourcePool.default()
        self.running = False
        self.raw_events: list[dict] = []
        self.events: list[EventEnvelope] = []
        self.incidents: dict[str, IncidentRecord] = {}
        self.second_emergency_fired = False

    # --- controls -----------------------------------------------------

    def start(self, session_seed: int, scenario_seed: int) -> None:
        self.reset(SeedConfig(session_seed=session_seed, scenario_seed=scenario_seed))
        self.running = True

    def pause(self) -> None:
        self.running = False

    def resume(self) -> None:
        self.running = True

    # --- event injection ----------------------------------------------

    def inject_incident(
        self,
        incident_type: IncidentType,
        zone: Zone,
        severity: SeverityHint | None = None,
        *,
        source_id: str = "sensor-auto-01",
        notes: str | None = None,
        multi_report: bool = False,
        bad_data_mode: InjectionMode | None = None,
    ) -> str:
        self.clock.tick()
        event = self.generator.make_incident(
            incident_type,
            zone,
            severity,
            source_id=source_id,
            when=self.clock.now,
            notes=notes,
        )
        raw = event.model_dump(mode="json")
        if bad_data_mode is not None:
            raw = apply_bad_data(raw, bad_data_mode)
        self.raw_events.append(raw)
        try:
            parsed = EventEnvelope.model_validate(raw)
        except ValueError:
            return event.incident_id  # hard-rejected at ingestion; id reserved
        self.events.append(parsed)
        self._register_incident(parsed)
        if multi_report:
            self._add_second_report(parsed, contradict=True)
        return event.incident_id

    def inject_bad_data(self, mode: InjectionMode, target_incident_id: str | None = None) -> str:
        if target_incident_id is None:
            incident_type = self.scenario_rng.choice(list(IncidentType))
            zone = self.scenario_rng.choice(list(Zone))
            return self.inject_incident(
                incident_type, zone, bad_data_mode=mode
            )
        match = [e for e in self.events if e.incident_id == target_incident_id]
        if not match:
            raise KeyError(f"unknown incident {target_incident_id}")
        base = match[0]
        self.clock.tick()
        second = self.generator.second_report(
            base, when=self.clock.now, source_id="sensor-inject-01", contradict=True
        )
        raw = apply_bad_data(second.model_dump(mode="json"), mode)
        self.raw_events.append(raw)
        try:
            parsed = EventEnvelope.model_validate(raw)
        except ValueError:
            return target_incident_id
        self.events.append(parsed)
        self._register_incident(parsed)
        return target_incident_id

    def second_emergency(
        self,
        incident_type: IncidentType = IncidentType.FIRE,
        zone: Zone = Zone.NORTH,
    ) -> str:
        """Second emergency while resources may be limited (plan Phase 1 scenario)."""
        self.second_emergency_fired = True
        return self.inject_incident(incident_type, zone, SeverityHint.SEVERE)

    # --- internals ----------------------------------------------------

    def _register_incident(self, event: EventEnvelope) -> None:
        existing = self.incidents.get(event.incident_id)
        if existing is None:
            self.incidents[event.incident_id] = IncidentRecord(
                incident_id=event.incident_id,
                incident_type=event.incident_type,
                zone=event.location.zone,
                lifecycle=IncidentLifecycle.DETECTED,
                validation_status=ValidationStatus.VALID,
                first_seen_simulated=event.simulated_time,
                latest_simulated=event.simulated_time,
                source_ids=[event.source_id],
                report_count=1,
            )
        else:
            existing.latest_simulated = event.simulated_time
            existing.report_count += 1
            if event.source_id not in existing.source_ids:
                existing.source_ids.append(event.source_id)

    def _add_second_report(self, first: EventEnvelope, *, contradict: bool) -> None:
        self.clock.tick()
        second = self.generator.second_report(
            first, when=self.clock.now, source_id="sensor-alt-02", contradict=contradict
        )
        self.raw_events.append(second.model_dump(mode="json"))
        self.events.append(second)
        self._register_incident(second)

    def reports_for(self, incident_id: str) -> list[EventEnvelope]:
        return [e for e in self.events if e.incident_id == incident_id]

    @property
    def simulated_time(self) -> datetime:
        return self.clock.now
