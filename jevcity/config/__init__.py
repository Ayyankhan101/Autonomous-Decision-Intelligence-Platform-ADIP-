"""Static Peshawar geography (workstream B1): zone polygons + unit stations."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jevcity.schemas import ResourceType, Zone

_CONFIG_PATH = Path(__file__).parent / "peshawar_zones.json"


@dataclass(frozen=True)
class Station:
    resource_id: str
    type: ResourceType
    zone: Zone
    lat: float
    lon: float
    label: str


@dataclass(frozen=True)
class PeshawarGeo:
    center_lat: float
    center_lon: float
    zone_centroids: dict[Zone, tuple[float, float]]
    zone_polygons: dict[Zone, list[tuple[float, float]]]
    stations: list[Station]


def load_peshawar_geo(path: Path | None = None) -> PeshawarGeo:
    raw = json.loads((path or _CONFIG_PATH).read_text())
    centroids: dict[Zone, tuple[float, float]] = {}
    polygons: dict[Zone, list[tuple[float, float]]] = {}
    for key, zdata in raw["zones"].items():
        zone = Zone(key)
        centroids[zone] = tuple(zdata["centroid"])
        polygons[zone] = [tuple(pt) for pt in zdata["polygon"]]
    stations = [
        Station(
            resource_id=s["resource_id"],
            type=ResourceType(s["type"]),
            zone=Zone(s["zone"]),
            lat=s["lat"],
            lon=s["lon"],
            label=s["label"],
        )
        for s in raw["stations"]
    ]
    return PeshawarGeo(
        center_lat=raw["center"]["lat"],
        center_lon=raw["center"]["lon"],
        zone_centroids=centroids,
        zone_polygons=polygons,
        stations=stations,
    )
