from __future__ import annotations
from routeiq.routing.scored_poi import ScoredPOI

DEFAULT_TOP_N = 5


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

        # Deduplicate by normalized name — keep lowest detour when same name appears multiple times
        seen: dict[str, ScoredPOI] = {}
        for sp in sorted(filtered, key=lambda s: s.detour_min):
            key = sp.poi.name.lower().strip()
            if key not in seen:
                seen[key] = sp
        filtered = list(seen.values())

        return sorted(filtered, key=lambda sp: sp.detour_min)[: self._top_n]
