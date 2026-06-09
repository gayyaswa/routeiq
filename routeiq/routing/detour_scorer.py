from __future__ import annotations
import math
from routeiq.graph.poi import POI
from routeiq.routing.scored_poi import ScoredPOI


class DetourScorer:
    """Scores POIs by straight-line round-trip detour from the nearest route node (Strategy pattern)."""

    def __init__(self, avg_speed_kmh: float = 50.0) -> None:
        self._avg_speed_kmh = avg_speed_kmh

    def score(
        self,
        pois: list[POI],
        route_coords: list[tuple[float, float]],
    ) -> list[ScoredPOI]:
        if not pois or not route_coords:
            return []
        results = []
        for poi in pois:
            min_dist = min(
                self._haversine_km(poi.lat, poi.lon, lat, lon)
                for lat, lon in route_coords
            )
            detour_km = 2.0 * min_dist
            detour_min = (detour_km / self._avg_speed_kmh) * 60.0
            results.append(ScoredPOI(poi=poi, detour_km=detour_km, detour_min=detour_min))
        return results

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return 2.0 * R * math.asin(math.sqrt(a))
