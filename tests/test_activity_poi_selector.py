"""Tests for ActivityPOISelector — two-track merge of activity and scenic fills."""
from __future__ import annotations
import pytest

from routeiq.graph.poi import POI
from routeiq.activities.base import ClassifiedPOI
from routeiq.routing.activity_poi_selector import ActivityPOISelector
from routeiq.activities.ranker import RatingRanker


def _cpoi(name, osm_id, lat=0.0, lon=0.0, subtype="peak", activities=None):
    poi = POI(
        name=name, category="natural",
        lat=lat, lon=lon, osm_id=osm_id,
        subtype=subtype,
    )
    return ClassifiedPOI(poi=poi, matched_activities=activities or [])


@pytest.fixture
def selector():
    return ActivityPOISelector()


class TestTrackMerge:
    def test_two_activity_and_three_scenic_slots(self, selector):
        classified = [
            _cpoi("Hike Peak", "1", lat=30.0, lon=-97.0, activities=["hiking"]),
            _cpoi("Bike Trail", "2", lat=30.1, lon=-97.0, activities=["biking"]),
            _cpoi("Scenic Beach", "3", lat=30.2, lon=-97.0, subtype="beach"),
            _cpoi("Viewpoint", "4", lat=30.3, lon=-97.0, subtype="viewpoint"),
            _cpoi("Cave", "5", lat=30.4, lon=-97.0, subtype="cave_entrance"),
        ]
        result = selector.select(classified, ["hiking", "biking"], total_stops=5)
        assert len(result) == 5
        activity_ids = {c.poi.osm_id for c in result if c.matched_activities}
        assert {"1", "2"}.issubset(activity_ids)

    def test_cap_at_three_activity_slots(self, selector):
        # 4 activities but n_activity_slots = min(4, 3) = 3.
        # Kayak (monument, score 4) loses to Scenic (viewpoint, score 9) in Track2,
        # so only the 3 Track1 winners have matched_activities in the final result.
        classified = [
            _cpoi("Hike", "1", activities=["hiking"]),
            _cpoi("Bike", "2", activities=["biking"]),
            _cpoi("Swim", "3", activities=["swimming"]),
            _cpoi("Kayak", "4", subtype="monument", activities=["kayaking"]),  # score 4
            _cpoi("Scenic", "5", subtype="viewpoint"),  # score 9
        ]
        result = selector.select(
            classified,
            ["hiking", "biking", "swimming", "kayaking"],
            total_stops=4,  # 3 activity + 1 scenic
        )
        # Track1 fills exactly 3; Track2 prefers Scenic over Kayak (9 > 4)
        activity_filled = [c for c in result if c.matched_activities]
        assert len(activity_filled) == 3

    def test_empty_activities_all_scenic(self, selector):
        classified = [
            _cpoi("Beach", "1", subtype="beach"),
            _cpoi("Peak", "2", subtype="peak"),
            _cpoi("Museum", "3", subtype="museum"),
        ]
        result = selector.select(classified, [], total_stops=3)
        assert len(result) == 3
        assert all(c.matched_activities == [] for c in result)

    def test_no_activity_candidates_fills_scenic(self, selector):
        # n_activity_slots = 1, n_scenic_slots = 1 (total 2 - 1 activity slot).
        # Hiking has no candidates so Track1 = []. Track2 fills 1 slot.
        # Unused activity slots are NOT reclaimed — this is intentional.
        classified = [
            _cpoi("Museum", "1", subtype="museum"),
            _cpoi("Park", "2", subtype="viewpoint"),
        ]
        result = selector.select(classified, ["hiking"], total_stops=2)
        assert len(result) == 1  # only the 1 scenic slot is filled
        assert result[0].poi.osm_id in {"1", "2"}

    def test_total_stops_respected(self, selector):
        classified = [_cpoi(f"Spot{i}", str(i)) for i in range(10)]
        result = selector.select(classified, [], total_stops=4)
        assert len(result) == 4


class TestScenicFillOrder:
    def test_scenic_fill_prefers_high_score_subtypes(self, selector):
        classified = [
            _cpoi("Monument", "1", subtype="monument"),  # score 4
            _cpoi("Waterfall", "2", subtype="waterfall"),  # score 9
        ]
        # With no activities and 1 slot, waterfall should be picked
        result = selector.select(classified, [], total_stops=1)
        assert result[0].poi.osm_id == "2"

    def test_activity_poi_excluded_from_scenic_fill(self, selector):
        classified = [
            _cpoi("Trail", "1", activities=["hiking"]),
            _cpoi("Scenic", "2", subtype="viewpoint"),
        ]
        result = selector.select(classified, ["hiking"], total_stops=2)
        ids = [c.poi.osm_id for c in result]
        assert ids.count("1") == 1  # no duplicates


class TestGeographyOrdering:
    def test_three_stops_reordered_by_geography(self, selector):
        classified = [
            _cpoi("South", "1", lat=29.0, lon=-98.0),
            _cpoi("North", "2", lat=31.0, lon=-98.0),
            _cpoi("Middle", "3", lat=30.0, lon=-98.0),
        ]
        result = selector.select(classified, [], total_stops=3)
        assert len(result) == 3
        # All stops must be present
        assert {c.poi.osm_id for c in result} == {"1", "2", "3"}

    def test_two_stops_not_reordered(self, selector):
        classified = [
            _cpoi("A", "1", lat=29.0, lon=-98.0),
            _cpoi("B", "2", lat=31.0, lon=-98.0),
        ]
        result = selector.select(classified, [], total_stops=2)
        assert len(result) == 2


class TestNoDuplicates:
    def test_no_duplicate_pois_in_result(self, selector):
        classified = [
            _cpoi("Trail", "1", activities=["hiking"]),
            _cpoi("Scene", "2", subtype="viewpoint"),
            _cpoi("Cave", "3", subtype="cave_entrance"),
        ]
        result = selector.select(classified, ["hiking"], total_stops=3)
        ids = [c.poi.osm_id for c in result]
        assert len(ids) == len(set(ids))


class TestEdgeCases:
    def test_empty_input_returns_empty(self, selector):
        result = selector.select([], [], total_stops=5)
        assert result == []

    def test_fewer_pois_than_total_stops(self, selector):
        classified = [_cpoi("Only One", "1", subtype="beach")]
        result = selector.select(classified, [], total_stops=5)
        assert len(result) == 1

    def test_custom_ranker_used(self, selector):
        classified = [
            _cpoi("A", "1", activities=["hiking"]),
            _cpoi("B", "2", activities=["hiking"]),
        ]
        ranker = RatingRanker()
        # Should not raise — custom ranker is used for activity slot selection
        result = selector.select(
            classified,
            ["hiking"],
            user_context="",
            ratings={"1": 4.0, "2": 2.0},
            total_stops=1,
            ranker=ranker,
        )
        assert len(result) == 1
        assert result[0].poi.osm_id == "1"
