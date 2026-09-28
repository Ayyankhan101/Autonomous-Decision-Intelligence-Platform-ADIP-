"""Resource inventory (plan §5.7): simulation owns statuses; guardrail allocates greedily."""
from __future__ import annotations

from jevcity.schemas import Resource, ResourceType, ResourceStatus, Zone

_DEFAULT_FLEET: list[tuple[str, ResourceType, Zone]] = [
    ("amb-01", ResourceType.AMBULANCE, Zone.NORTH),
    ("amb-02", ResourceType.AMBULANCE, Zone.SOUTH),
    ("amb-03", ResourceType.AMBULANCE, Zone.EAST),
    ("amb-04", ResourceType.AMBULANCE, Zone.WEST),
    ("amb-05", ResourceType.AMBULANCE, Zone.CENTRAL),
    ("fire-01", ResourceType.FIRE_TRUCK, Zone.NORTH),
    ("fire-02", ResourceType.FIRE_TRUCK, Zone.SOUTH),
    ("fire-03", ResourceType.FIRE_TRUCK, Zone.CENTRAL),
    ("pol-01", ResourceType.POLICE_UNIT, Zone.NORTH),
    ("pol-02", ResourceType.POLICE_UNIT, Zone.SOUTH),
    ("pol-03", ResourceType.POLICE_UNIT, Zone.EAST),
    ("pol-04", ResourceType.POLICE_UNIT, Zone.WEST),
    ("pol-05", ResourceType.POLICE_UNIT, Zone.CENTRAL),
    ("fld-01", ResourceType.FLOOD_RESPONSE_UNIT, Zone.EAST),
    ("fld-02", ResourceType.FLOOD_RESPONSE_UNIT, Zone.WEST),
    ("tmu-01", ResourceType.TRAFFIC_MANAGEMENT_UNIT, Zone.CENTRAL),
    ("tmu-02", ResourceType.TRAFFIC_MANAGEMENT_UNIT, Zone.NORTH),
]


class ResourcePool:
    def __init__(self, resources: list[Resource] | None = None) -> None:
        fleet = resources if resources is not None else [
            Resource(resource_id=rid, type=t, zone=z) for rid, t, z in _DEFAULT_FLEET
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
