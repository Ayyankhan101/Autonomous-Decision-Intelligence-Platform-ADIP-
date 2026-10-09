"""Greedy resource allocation (plan §5.7): priority/confidence/impact already decided;
allocator picks best available — and admits contention instead of pretending it succeeded.

Policy position (enhancement 2): RESPONSE_TIME (and EQUITY, whose lever is priority)
keep the baseline local-first pick; ECO picks the candidate with the highest eco_score.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from jevcity.schemas import (
    DecisionRecord,
    IncidentType,
    PolicyPosition,
    Priority,
    ResourceType,
)
from jevcity.simulation.resource_pool import ResourcePool

_PRIORITY_RANK = {Priority.CRITICAL: 3, Priority.HIGH: 2, Priority.MEDIUM: 1, Priority.LOW: 0}

FALLBACK_RESOURCE: dict[IncidentType, list[ResourceType]] = {
    IncidentType.ACCIDENT: [ResourceType.AMBULANCE, ResourceType.POLICE_UNIT],
    IncidentType.FIRE: [ResourceType.FIRE_TRUCK, ResourceType.AMBULANCE],
    IncidentType.FLOOD: [ResourceType.FLOOD_RESPONSE_UNIT, ResourceType.POLICE_UNIT],
    IncidentType.TRAFFIC_SPIKE: [ResourceType.TRAFFIC_MANAGEMENT_UNIT, ResourceType.POLICE_UNIT],
}


@dataclass
class AllocationResult:
    assigned_ids: list[str] = field(default_factory=list)
    available_ids: list[str] = field(default_factory=list)
    contention: bool = False
    requested_types: list[ResourceType] = field(default_factory=list)


def order_queue(decisions: list[DecisionRecord]) -> list[DecisionRecord]:
    """Greedy order: priority desc, overall confidence desc, waiting time desc
    (earliest decision first among equals)."""
    return sorted(
        decisions,
        key=lambda d: (
            -_PRIORITY_RANK[d.priority],
            -(d.overall_confidence or 0.0),
            d.decision_time_simulated,
        ),
    )


def allocate_for_incident(
    pool: ResourcePool,
    *,
    incident_id: str,
    zone,
    incident_type: IncidentType,
    priority: Priority,
    recommended: list[ResourceType],
    policy_position: PolicyPosition = PolicyPosition.RESPONSE_TIME,
) -> AllocationResult:
    types = recommended or FALLBACK_RESOURCE.get(incident_type, [])
    result = AllocationResult(requested_types=list(types))
    result.available_ids = [
        r.resource_id
        for r in pool.available()
        if not types or r.type in types
    ]
    if priority == Priority.LOW:
        result.available_ids = [r.resource_id for r in pool.available()]
        return result

    for wanted in types:
        candidates = [
            r
            for r in pool.available(wanted)
        ]
        if not candidates:
            continue
        if policy_position == PolicyPosition.ECO:
            # Eco-optimisation: electric-first among all candidate units.
            pick = sorted(candidates, key=lambda r: (-r.eco_score, r.resource_id))[0]
        else:
            same_zone = [r for r in candidates if r.zone == zone]
            pick = sorted(same_zone or candidates, key=lambda r: r.resource_id)[0]
        pool.assign(pick.resource_id, incident_id)
        result.assigned_ids.append(pick.resource_id)
        result.available_ids = [
            r.resource_id for r in pool.available() if not types or r.type in types
        ]
        return result

    result.contention = not result.assigned_ids
    return result
