"""Tests for select_pois_for_day LangChain tool."""
from __future__ import annotations
import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from routeiq.graph.poi import POI
from routeiq.activities.base import ClassifiedPOI

# Import triggers sys.modules population so patch.object can resolve the module.
from routeiq.agent.tools.select_pois_for_day import select_pois_for_day
_mod = sys.modules["routeiq.agent.tools.select_pois_for_day"]


def _poi(name, osm_id, subtype=None, category="tourism"):
    return POI(name=name, category=category, lat=30.0, lon=-97.0, osm_id=osm_id, subtype=subtype)


def _cpoi(poi, activities=None):
    return ClassifiedPOI(poi=poi, matched_activities=activities or [])


def _invoke(city="Austin, TX", activities=None, user_context="", total_stops=3):
    return json.loads(select_pois_for_day.invoke({
        "city": city,
        "requested_activities": activities or [],
        "user_context": user_context,
        "total_stops": total_stops,
    }))


class TestOutputShape:
    def test_returns_json_array(self):
        pois = [_poi("Trail Head", "1", subtype="peak")]
        classified = [_cpoi(pois[0], activities=["hiking"])]
        clf = MagicMock()
        clf.classify_batch.return_value = classified
        with patch.object(_mod, "get_kg") as mock_kg, \
             patch("routeiq.activities.factory.create_activity_classifier", return_value=clf):
            mock_kg.return_value.get_pois_for_city.return_value = pois
            result = _invoke(activities=["hiking"])
        assert isinstance(result, list)

    def test_output_includes_required_fields(self):
        pois = [_poi("Trail", "1", subtype="peak")]
        classified = [_cpoi(pois[0], activities=["hiking"])]
        clf = MagicMock()
        clf.classify_batch.return_value = classified
        with patch.object(_mod, "get_kg") as mock_kg, \
             patch("routeiq.activities.factory.create_activity_classifier", return_value=clf):
            mock_kg.return_value.get_pois_for_city.return_value = pois
            result = _invoke(activities=["hiking"], total_stops=1)
        assert len(result) > 0
        item = result[0]
        assert "name" in item
        assert "matched_activities" in item
        assert "track" in item

    def test_track_field_values_are_valid(self):
        pois = [
            _poi("Trail", "1", subtype="peak"),
            _poi("Museum", "2", subtype="museum"),
        ]
        classified = [
            _cpoi(pois[0], activities=["hiking"]),
            _cpoi(pois[1]),
        ]
        clf = MagicMock()
        clf.classify_batch.return_value = classified
        with patch.object(_mod, "get_kg") as mock_kg, \
             patch("routeiq.activities.factory.create_activity_classifier", return_value=clf):
            mock_kg.return_value.get_pois_for_city.return_value = pois
            result = _invoke(activities=["hiking"], total_stops=2)
        for item in result:
            assert item["track"] in ("activity", "scenic")

    def test_activity_matched_poi_has_activity_track(self):
        pois = [_poi("Trail", "1", subtype="peak")]
        classified = [_cpoi(pois[0], activities=["hiking"])]
        clf = MagicMock()
        clf.classify_batch.return_value = classified
        with patch.object(_mod, "get_kg") as mock_kg, \
             patch("routeiq.activities.factory.create_activity_classifier", return_value=clf):
            mock_kg.return_value.get_pois_for_city.return_value = pois
            result = _invoke(activities=["hiking"], total_stops=1)
        activity_items = [r for r in result if "hiking" in r.get("matched_activities", [])]
        assert len(activity_items) >= 1
        assert all(item["track"] == "activity" for item in activity_items)


class TestEmptyAndEdge:
    def test_empty_pois_returns_empty_json_array(self):
        with patch.object(_mod, "get_kg") as mock_kg:
            mock_kg.return_value.get_pois_for_city.return_value = []
            result = _invoke(city="Ghost Town", activities=["hiking"])
        assert result == []

    def test_activities_empty_all_scenic_track(self):
        pois = [_poi("Museum", "1", subtype="museum"), _poi("Viewpoint", "2", subtype="viewpoint")]
        classified = [_cpoi(p) for p in pois]
        clf = MagicMock()
        clf.classify_batch.return_value = classified
        with patch.object(_mod, "get_kg") as mock_kg, \
             patch("routeiq.activities.factory.create_activity_classifier", return_value=clf):
            mock_kg.return_value.get_pois_for_city.return_value = pois
            result = _invoke(activities=[], total_stops=2)
        assert all(item["track"] == "scenic" for item in result)
        assert all(item["matched_activities"] == [] for item in result)

    def test_total_stops_limits_output(self):
        pois = [_poi(f"Spot{i}", str(i)) for i in range(10)]
        classified = [_cpoi(p) for p in pois]
        clf = MagicMock()
        clf.classify_batch.return_value = classified
        with patch.object(_mod, "get_kg") as mock_kg, \
             patch("routeiq.activities.factory.create_activity_classifier", return_value=clf):
            mock_kg.return_value.get_pois_for_city.return_value = pois
            result = _invoke(activities=[], total_stops=3)
        assert len(result) == 3
