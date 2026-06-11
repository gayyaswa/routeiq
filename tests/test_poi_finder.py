import numpy as np
import pytest
import geopandas as gpd
from shapely.geometry import Point, Polygon
from unittest.mock import patch

from routeiq.graph import POIFinder
from routeiq.graph.poi_finder import OverpassUnavailableError


# Route along lon=-98.0, lat 29.5→29.6 — buffer ≈ 0.045 deg (~5 km)
ROUTE = [(29.5, -98.0), (29.6, -98.0)]


def _make_gdf():
    """Mock GeoDataFrame with four features: inside, outside, unnamed, polygon."""
    poly_inside = Polygon([
        (-98.01, 29.54), (-97.99, 29.54),
        (-97.99, 29.56), (-98.01, 29.56),
    ])
    return gpd.GeoDataFrame(
        {
            "geometry": [
                Point(-98.0, 29.55),   # on route — inside buffer
                Point(-97.5, 29.55),   # far east — outside buffer
                Point(-98.0, 29.55),   # inside but no name
                poly_inside,           # polygon, centroid inside
            ],
            "name": ["San Jose Mission", "Far Away Place", np.nan, "Historic Fort"],
            "historic": ["fort", np.nan, np.nan, "fort"],
            "tourism": [np.nan, "attraction", np.nan, np.nan],
            "natural": [np.nan, np.nan, np.nan, np.nan],
            "wikipedia": ["en:San_Jose_Mission", np.nan, np.nan, np.nan],
        },
        geometry="geometry",
        crs="EPSG:4326",
    )


@pytest.fixture
def finder(tmp_path):
    return POIFinder(buffer_km=5.0, cache_dir=str(tmp_path))


class TestPOIFinderBasic:
    def test_inside_buffer_returned(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        names = [p.name for p in pois]
        assert "San Jose Mission" in names

    def test_outside_buffer_excluded(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        names = [p.name for p in pois]
        assert "Far Away Place" not in names

    def test_nan_name_skipped(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        assert all(p.name for p in pois)

    def test_polygon_centroid_included(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        names = [p.name for p in pois]
        assert "Historic Fort" in names

    def test_wikipedia_tag_preserved(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        mission = next(p for p in pois if p.name == "San Jose Mission")
        assert mission.wikipedia_tag == "en:San_Jose_Mission"

    def test_wikipedia_tag_none_when_missing(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        fort = next(p for p in pois if p.name == "Historic Fort")
        assert fort.wikipedia_tag is None

    def test_category_historic_priority(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        mission = next(p for p in pois if p.name == "San Jose Mission")
        assert mission.category == "historic"

    def test_subtype_populated_from_osm_value(self, finder):
        with patch("osmnx.features_from_bbox", return_value=_make_gdf()):
            pois = finder.find_pois(ROUTE)
        mission = next(p for p in pois if p.name == "San Jose Mission")
        assert mission.subtype == "fort"


class TestPOIFinderEdgeCases:
    def test_empty_route_returns_empty(self, finder):
        pois = finder.find_pois([])
        assert pois == []

    def test_osmnx_exception_raises_overpass_error(self, finder):
        with patch("osmnx.features_from_bbox", side_effect=Exception("network error")):
            with pytest.raises(OverpassUnavailableError):
                finder.find_pois(ROUTE)

    def test_progress_fn_called_on_mirror_failure(self, finder):
        calls = []
        with patch("osmnx.features_from_bbox", side_effect=Exception("down")):
            with pytest.raises(OverpassUnavailableError):
                finder.find_pois(ROUTE, progress_fn=lambda msg: calls.append(msg))
        assert len(calls) > 0
        assert any("unavailable" in c.lower() or "backup" in c.lower() for c in calls)
