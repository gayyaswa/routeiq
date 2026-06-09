from __future__ import annotations
from dataclasses import dataclass
from routeiq.graph.poi import POI


@dataclass
class ScoredPOI:
    """POI with precomputed detour cost from the nearest route node (dataclass)."""

    poi: POI
    detour_km: float
    detour_min: float
