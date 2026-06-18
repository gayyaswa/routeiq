"""Tests for Day Trip agent tools."""
import dataclasses
import json
import sys
import pytest
from unittest.mock import MagicMock, patch

from routeiq.graph.poi import POI

# Import tools — this populates sys.modules with the submodules.
# We use sys.modules references for patching because __init__.py's
# `from ... import <tool>` shadows the submodule name on the package,
# making patch("routeiq.agent.tools.<module>.<Class>") resolve to the
# StructuredTool object rather than the module.
from routeiq.agent.tools.get_travel_time import get_travel_time
from routeiq.agent.tools.estimate_visit import estimate_visit_duration
from routeiq.agent.tools.find_city_pois import find_city_pois as find_city_pois_tool
from routeiq.agent.tools.enrich_poi_details import enrich_poi_details as enrich_poi_details_tool

_fcp_mod = sys.modules["routeiq.agent.tools.find_city_pois"]
_epd_mod = sys.modules["routeiq.agent.tools.enrich_poi_details"]

_SF_POI = POI(name="Alcatraz Island", category="tourism", lat=37.8267, lon=-122.4233,
              osm_id="way/123", wikipedia_tag="en:Alcatraz_Island")


class TestGetTravelTime:
    def test_returns_json_with_required_keys(self):
        result = json.loads(get_travel_time.invoke({"lat1": 37.77, "lon1": -122.41,
                                                     "lat2": 37.80, "lon2": -122.42}))
        assert "distance_km" in result
        assert "estimated_minutes" in result

    def test_same_point_overhead_only(self):
        result = json.loads(get_travel_time.invoke({"lat1": 37.77, "lon1": -122.41,
                                                     "lat2": 37.77, "lon2": -122.41}))
        assert result["distance_km"] == 0.0
        assert result["estimated_minutes"] == pytest.approx(5.0)   # overhead only

    def test_distance_positive_for_different_points(self):
        result = json.loads(get_travel_time.invoke({"lat1": 37.77, "lon1": -122.41,
                                                     "lat2": 37.87, "lon2": -122.41}))
        assert result["distance_km"] > 0
        assert result["estimated_minutes"] > 5.0


class TestEstimateVisitDuration:
    def test_museum_returns_90(self):
        result = json.loads(estimate_visit_duration.invoke({"category": "tourism", "subtype": "museum"}))
        assert result["estimated_minutes"] == 90

    def test_viewpoint_returns_30(self):
        result = json.loads(estimate_visit_duration.invoke({"category": "tourism", "subtype": "viewpoint"}))
        assert result["estimated_minutes"] == 30

    def test_unknown_subtype_returns_default(self):
        result = json.loads(estimate_visit_duration.invoke({"category": "tourism", "subtype": "unknown_xyz"}))
        assert result["estimated_minutes"] == 45

    def test_case_insensitive(self):
        result = json.loads(estimate_visit_duration.invoke({"category": "tourism", "subtype": "MUSEUM"}))
        assert result["estimated_minutes"] == 90


class TestFindCityPois:
    def test_returns_json_array(self):
        with patch.object(_fcp_mod, "get_kg") as mock_get_kg:
            mock_get_kg.return_value.get_pois_for_city.return_value = [_SF_POI]
            result = json.loads(find_city_pois_tool.invoke({"city": "San Francisco, CA", "categories": []}))
        assert isinstance(result, list)
        assert result[0]["name"] == "Alcatraz Island"

    def test_category_filter_applied(self):
        historic_poi = POI(name="Fort Point", category="historic", lat=37.81, lon=-122.47, osm_id="way/456")
        with patch.object(_fcp_mod, "get_kg") as mock_get_kg:
            mock_get_kg.return_value.get_pois_for_city.return_value = [_SF_POI, historic_poi]
            result = json.loads(find_city_pois_tool.invoke({"city": "San Francisco, CA", "categories": ["historic"]}))
        assert len(result) == 1
        assert result[0]["name"] == "Fort Point"

    def test_empty_categories_returns_all(self):
        historic_poi = POI(name="Fort Point", category="historic", lat=37.81, lon=-122.47, osm_id="way/456")
        with patch.object(_fcp_mod, "get_kg") as mock_get_kg:
            mock_get_kg.return_value.get_pois_for_city.return_value = [_SF_POI, historic_poi]
            result = json.loads(find_city_pois_tool.invoke({"city": "San Francisco, CA", "categories": []}))
        assert len(result) == 2

    def test_capped_at_100(self):
        many_pois = [
            POI(name=f"POI {i}", category="tourism", lat=37.77, lon=-122.41, osm_id=f"way/{i}")
            for i in range(150)
        ]
        with patch.object(_fcp_mod, "get_kg") as mock_get_kg:
            mock_get_kg.return_value.get_pois_for_city.return_value = many_pois
            result = json.loads(find_city_pois_tool.invoke({"city": "San Francisco, CA", "categories": []}))
        assert len(result) == 100


class TestEnrichPoiDetails:
    def test_returns_description_and_image_url(self):
        with patch.object(_epd_mod, "WikipediaFetcher") as MockFetcher:
            def fake_enrich(poi):
                poi.description = "Historic island prison."
                poi.image_url = "https://example.com/alcatraz.jpg"
            MockFetcher.return_value.enrich.side_effect = fake_enrich

            result = json.loads(enrich_poi_details_tool.invoke(
                {"poi_name": "Alcatraz Island", "city": "San Francisco, CA"}
            ))

        assert result["description"] == "Historic island prison."
        assert result["image_url"] == "https://example.com/alcatraz.jpg"

    def test_returns_nulls_when_not_found(self):
        with patch.object(_epd_mod, "WikipediaFetcher") as MockFetcher:
            MockFetcher.return_value.enrich.return_value = None  # enrich mutates in place, no-op here

            result = json.loads(enrich_poi_details_tool.invoke(
                {"poi_name": "Nonexistent Place XYZ", "city": "San Francisco, CA"}
            ))

        assert result["description"] is None
        assert result["image_url"] is None
