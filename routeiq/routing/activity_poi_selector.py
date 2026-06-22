from __future__ import annotations
from routeiq.activities.base import ClassifiedPOI
from routeiq.activities.ranker import ActivityRanker, create_ranker

# Mirrors _SCENIC_SCORE in poi_selector.py — same tier values.
_SCENIC_SCORE: dict[str, int] = {
    "waterfall": 9, "volcano": 9, "beach": 9, "cape": 9,
    "peak": 8, "cliff": 8, "glacier": 8, "hot_spring": 8,
    "bay": 7, "cave_entrance": 7, "wood": 6,
    "viewpoint": 9, "lighthouse": 8,
    "attraction": 7, "museum": 6, "winery": 6,
    "aquarium": 6, "zoo": 5, "theme_park": 5,
    "monument": 4,
    "castle": 8, "fort": 7, "ruins": 7, "archaeological_site": 7,
    "manor": 6, "battlefield": 6,
    "memorial": 3,
}
_DEFAULT_SCENIC = 5


def _scenic_score(c: ClassifiedPOI) -> int:
    return _SCENIC_SCORE.get(c.poi.subtype or "", _DEFAULT_SCENIC)


class ActivityPOISelector:
    """Merges activity-matched (Track 1) and scenic-fill (Track 2) POIs into an itinerary."""

    def select(
        self,
        classified_pois: list[ClassifiedPOI],
        requested_activities: list[str],
        user_context: str = "",
        ratings: dict[str, float] | None = None,
        total_stops: int = 5,
        ranker: ActivityRanker | None = None,
    ) -> list[ClassifiedPOI]:
        ratings = ratings or {}
        n_activity_slots = min(len(requested_activities), 3) if requested_activities else 0
        n_scenic_slots = total_stops - n_activity_slots

        track1 = self._build_track1(
            classified_pois, requested_activities, n_activity_slots,
            user_context, ratings, ranker,
        )
        used_ids = {c.poi.osm_id for c in track1}
        track2 = self._build_track2(classified_pois, used_ids, n_scenic_slots)

        return self._order_by_geography(track1 + track2)

    def _build_track1(
        self,
        classified_pois, requested_activities, n_slots,
        user_context, ratings, ranker,
    ) -> list[ClassifiedPOI]:
        if not requested_activities or n_slots == 0:
            return []

        selected: list[ClassifiedPOI] = []

        for activity in requested_activities:
            if len(selected) >= n_slots:
                break
            candidates = [
                c for c in classified_pois
                if activity in c.matched_activities
                and c.poi.osm_id not in {s.poi.osm_id for s in selected}
            ]
            if not candidates:
                continue

            active_ranker = ranker or create_ranker(user_context, bool(ratings))
            ranked = active_ranker.rank(candidates, activity, user_context, ratings)
            if ranked:
                selected.append(ranked[0])

        return selected

    def _build_track2(
        self, classified_pois, used_ids: set[str], n_slots: int
    ) -> list[ClassifiedPOI]:
        remaining = [c for c in classified_pois if c.poi.osm_id not in used_ids]
        remaining.sort(key=_scenic_score, reverse=True)
        return remaining[:n_slots]

    def _order_by_geography(self, stops: list[ClassifiedPOI]) -> list[ClassifiedPOI]:
        if len(stops) <= 2:
            return stops
        unvisited = list(stops)
        ordered = [min(unvisited, key=lambda c: -c.poi.lat)]
        unvisited.remove(ordered[0])
        while unvisited:
            last = ordered[-1]
            nearest = min(
                unvisited,
                key=lambda c: (c.poi.lat - last.poi.lat) ** 2 + (c.poi.lon - last.poi.lon) ** 2,
            )
            ordered.append(nearest)
            unvisited.remove(nearest)
        return ordered
