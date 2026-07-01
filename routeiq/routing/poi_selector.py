from __future__ import annotations
import math
from routeiq.routing.scored_poi import ScoredPOI
from routeiq.routing.scenic_scores import get_scenic_score

DEFAULT_TOP_N = 5
# Minimum straight-line distance between any two selected POIs.
# Prevents the selector from filling all N slots with monuments from the
# same city block when the route passes through a dense urban area.
_MIN_SPREAD_KM = 2.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _scenic(sp: ScoredPOI) -> int:
    return get_scenic_score(sp.poi.subtype)


class POISelector:
    """Selects top-N POIs from a scored list with optional category preference filtering (Strategy pattern)."""

    def __init__(self, top_n: int = DEFAULT_TOP_N) -> None:
        self._top_n = top_n

    def select(
        self,
        scored_pois: list[ScoredPOI],
        preferences: list[str],
    ) -> list[ScoredPOI]:
        if not scored_pois:
            return []
        prefs = [p.lower().strip() for p in preferences]
        if prefs:
            filtered = [sp for sp in scored_pois if sp.poi.category.lower() in prefs]
            if not filtered:
                filtered = scored_pois  # silent fallback: no category match → use all
        else:
            filtered = scored_pois

        # Deduplicate by normalized name — keep best-ranked when same name appears multiple times
        seen: dict[str, ScoredPOI] = {}
        for sp in sorted(filtered, key=lambda s: s.detour_min):
            key = sp.poi.name.lower().strip()
            if key not in seen:
                seen[key] = sp

        # Three-tier sort:
        #   1. OSM wikipedia_tag presence — crowd-sourced notability signal
        #   2. Scenic/experiential score per OSM subtype (higher = more scenic)
        #   3. Detour cost — tiebreaker within equally notable, equally scenic POIs
        deduped = sorted(
            seen.values(),
            key=lambda sp: (0 if sp.poi.wikipedia_tag else 1, -_scenic(sp), sp.detour_min),
        )

        # Greedy geographic spread: each selected POI must be at least _MIN_SPREAD_KM
        # from every already-selected POI. This prevents filling all slots with stops
        # from the same neighbourhood when the route passes through a dense urban area.
        selected: list[ScoredPOI] = []
        for sp in deduped:
            if all(
                _haversine_km(sp.poi.lat, sp.poi.lon, s.poi.lat, s.poi.lon) >= _MIN_SPREAD_KM
                for s in selected
            ):
                selected.append(sp)
            if len(selected) >= self._top_n:
                break
        return selected
