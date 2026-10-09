"""Resource inventory (plan §5.7): simulation owns statuses; guardrail allocates greedily."""
from __future__ import annotations

from jevcity.schemas import Resource, ResourceType, ResourceStatus, Zone

# (resource_id, type, zone, eco_score) — eco_score ∈ [0, 1]: 1 = electric/zero-emission
# response vehicle, 0 = highest-emission. Consumed only under the ECO policy position
# (enhancement 2).
_DEFAULT_FLEET: list[tuple[str, ResourceType, Zone, float]] = [
    ("amb-01", ResourceType.AMBULANCE, Zone.NORTH, 0.9),
    ("amb-02", ResourceType.AMBULANCE, Zone.SOUTH, 0.1),
    ("amb-03", ResourceType.AMBULANCE, Zone.EAST, 0.7),
    ("amb-04", ResourceType.AMBULANCE, Zone.WEST, 0.2),
    ("amb-05", ResourceType.AMBULANCE, Zone.CENTRAL, 0.8),
    ("fire-01", ResourceType.FIRE_TRUCK, Zone.NORTH, 0.9),
    ("fire-02", ResourceType.FIRE_TRUCK, Zone.SOUTH, 0.3),
    ("fire-03", ResourceType.FIRE_TRUCK, Zone.CENTRAL, 0.6),
    ("pol-01", ResourceType.POLICE_UNIT, Zone.NORTH, 0.8),
    ("pol-02", ResourceType.POLICE_UNIT, Zone.SOUTH, 0.2),
    ("pol-03", ResourceType.POLICE_UNIT, Zone.EAST, 0.7),
    ("pol-04", ResourceType.POLICE_UNIT, Zone.WEST, 0.1),
    ("pol-05", ResourceType.POLICE_UNIT, Zone.CENTRAL, 0.9),
    ("fld-01", ResourceType.FLOOD_RESPONSE_UNIT, Zone.EAST, 0.75),
    ("fld-02", ResourceType.FLOOD_RESPONSE_UNIT, Zone.WEST, 0.4),
    ("tmu-01", ResourceType.TRAFFIC_MANAGEMENT_UNIT, Zone.CENTRAL, 0.85),
    ("tmu-02", ResourceType.TRAFFIC_MANAGEMENT_UNIT, Zone.NORTH, 0.3),
]


class ResourcePool:
    def __init__(self, resources: list[Resource] | None = None) -> None:
        fleet = resources if resources is not None else [
            Resource(resource_id=rid, type=t, zone=z, eco_score=eco)
            for rid, t, z, eco in _DEFAULT_FLEET
        ]
        self._by_id: dict[str, Resource] = {r.resource_id: r for r in fleet}

    @classmethod
    def default(cls) -> ResourcePool:
        return cls()

    def all(self) -> list[Resource]:
        return list(self._by_id.values())

    def get(self, resource_id: str) -> Resource | None:
        return self._by_id.get(resource_id)

    def available(
        self, type_: ResourceType | None = None, zone: Zone | None = None
    ) -> list[Resource]:
        out = [
            r
            for r in self._by_id.values()
            if r.status == ResourceStatus.AVAILABLE
            and (type_ is None or r.type == type_)
            and (zone is None or r.zone == zone)
        ]
        return sorted(out, key=lambda r: r.resource_id)

    def available_count(self, type_: ResourceType | None = None) -> int:
        return len(self.available(type_))

    def counts_available_by_type(self) -> dict[ResourceType, int]:
        counts = dict.fromkeys(ResourceType, 0)
        for r in self.all():
            if r.status == ResourceStatus.AVAILABLE:
                counts[r.type] += 1
        return counts

    def assign(self, resource_id: str, incident_id: str) -> Resource:
        res = self._require(resource_id)
        if res.status != ResourceStatus.AVAILABLE:
            raise ValueError(f"resource {resource_id} not available (status={res.status})")
        res.status = ResourceStatus.ASSIGNED
        res.assigned_incident_id = incident_id
        return res

    def set_busy(self, resource_id: str) -> Resource:
        res = self._require(resource_id)
        res.status = ResourceStatus.BUSY
        return res

    def release(self, resource_id: str) -> Resource:
        res = self._require(resource_id)
        res.status = ResourceStatus.AVAILABLE
        res.assigned_incident_id = None
        return res

    def take_offline(self, resource_id: str) -> Resource:
        res = self._require(resource_id)
        res.status = ResourceStatus.OFFLINE
        res.assigned_incident_id = None
        return res

    def remove(self, resource_id: str) -> Resource:
        """What-If: pull a resource from the fleet (sandbox only)."""
        return self._by_id.pop(resource_id)

    def _require(self, resource_id: str) -> Resource:
        res = self._by_id.get(resource_id)
        if res is None:
            raise KeyError(f"unknown resource {resource_id}")
        return res
