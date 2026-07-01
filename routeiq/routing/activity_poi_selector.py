from __future__ import annotations
from routeiq.activities.base import ClassifiedPOI
from routeiq.activities.ranker import ActivityRanker, create_ranker
from routeiq.routing.scenic_scores import get_scenic_score


def _scenic_score(c: ClassifiedPOI) -> int:
    return get_scenic_score(c.poi.subtype)


def _slots_for_activity(candidates: list) -> int:
    n = len(candidates)
    return 3 if n >= 11 else (2 if n >= 4 else (1 if n else 0))


def _scale_slots_proportional(raw_slots: dict[str, int], budget: int) -> dict[str, int]:
    result = dict.fromkeys(raw_slots, 0)
    if budget <= 0:
        return result
    # Only activities with candidates can receive slots; sort by density desc
    active = sorted(((act, w) for act, w in raw_slots.items() if w > 0), key=lambda x: -x[1])
    if not active:
        return result
    total_weight = sum(w for _, w in active)
    remaining = budget
    for i, (act, w) in enumerate(active):
        acts_left = len(active) - i
        if remaining <= 0:
            break
        if acts_left > remaining:
            # Budget scarce — give 1 to this activity and move on
            result[act] = 1
            remaining -= 1
        else:
            # Reserve at least 1 for each remaining activity, then give proportional share
            share = max(1, round(w / total_weight * budget))
            share = min(share, remaining - (acts_left - 1))
            result[act] = share
            remaining -= share
            total_weight -= w
    return result


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

        if requested_activities:
            candidates_by_activity = {
                act: [c for c in classified_pois if act in c.matched_activities]
                for act in requested_activities
            }
            raw_slots = {
                act: _slots_for_activity(candidates_by_activity[act])
                for act in requested_activities
            }
            # Cap activity slots at 2 total so scenic fills dominate the itinerary.
            activity_budget = min(2, max(1, total_stops - 1))
            per_activity_slots = _scale_slots_proportional(raw_slots, activity_budget)
        else:
            per_activity_slots = {}

        track1 = self._build_track1(
            classified_pois, requested_activities, per_activity_slots,
            user_context, ratings, ranker,
        )
        used_ids = {c.poi.osm_id for c in track1}
        # Use actual track1 length, not budgeted slots — unused activity slots spill to scenic.
        n_scenic_slots = total_stops - len(track1)
        track2 = self._build_track2(classified_pois, used_ids, n_scenic_slots)

        return self._order_by_geography(track1 + track2)

    def _build_track1(
        self,
        classified_pois,
        requested_activities,
        per_activity_slots: dict[str, int],
        user_context,
        ratings,
        ranker,
    ) -> list[ClassifiedPOI]:
        if not requested_activities or not per_activity_slots:
            return []

        selected: list[ClassifiedPOI] = []

        for activity in requested_activities:
            n = per_activity_slots.get(activity, 0)
            if n == 0:
                continue
            candidates = [
                c for c in classified_pois
                if activity in c.matched_activities
                and c.poi.osm_id not in {s.poi.osm_id for s in selected}
            ]
            if not candidates:
                continue

            active_ranker = ranker or create_ranker(user_context, bool(ratings))
            ranked = active_ranker.rank(candidates, activity, user_context, ratings)
            selected.extend(ranked[:n])

        return selected

    def _build_track2(
        self, classified_pois, used_ids: set[str], n_slots: int
    ) -> list[ClassifiedPOI]:
        remaining = [c for c in classified_pois if c.poi.osm_id not in used_ids]
        # Sort by (wikipedia notability, scenic tier) so fills are the most visited/notable
        # POIs from the city pool, not just the best OSM subtype tier.
        remaining.sort(key=lambda c: (0 if c.poi.wikipedia_tag else 1, -_scenic_score(c)))
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
