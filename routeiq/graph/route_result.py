from __future__ import annotations
from dataclasses import dataclass


@dataclass
class RouteResult:
    """Typed result from A* pathfinding over an OSM road network (dataclass)."""

    route_nodes: list[int]
    route_coords: list[tuple[float, float]]  # (lat, lon)
    length_km: float
    drive_time_min: float
