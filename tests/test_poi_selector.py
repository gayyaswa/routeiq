import pytest

from routeiq.graph import POI
from routeiq.routing import ScoredPOI, POISelector


def _scored(name, category, detour_km, detour_min, lat=29.5, lon=-98.0):
    poi = POI(name=name, category=category, lat=lat, lon=lon, osm_id="1")
    return ScoredPOI(poi=poi, detour_km=detour_km, detour_min=detour_min)


@pytest.fixture
def sample_pois():
    # Each POI is ~2.2 km apart (0.02° latitude steps) so all pass the spread check.
    return [
        _scored("Alamo",                  "historic", 2.0, 2.4,  lat=29.50),
        _scored("Natural Bridge Caverns", "tourism",  5.0, 6.0,  lat=29.52),
        _scored("Enchanted Rock",         "natural",  8.0, 9.6,  lat=29.54),
        _scored("San Jose Mission",       "historic", 1.0, 1.2,  lat=29.56),
        _scored("Barton Springs",         "natural", 12.0, 14.4, lat=29.58),
    ]


class TestPOISelectorSelect:
    def test_top_n_limits_results(self, sample_pois):
        selector = POISelector(top_n=2)
        result = selector.select(sample_pois, preferences=[])
        assert len(result) == 2

    def test_sorted_ascending_by_detour_min(self, sample_pois):
        selector = POISelector()
        result = selector.select(sample_pois, preferences=[])
        detours = [sp.detour_min for sp in result]
        assert detours == sorted(detours)

    def test_preference_filters_category(self, sample_pois):
        selector = POISelector()
        result = selector.select(sample_pois, preferences=["historic"])
        assert all(sp.poi.category == "historic" for sp in result)

    def test_multiple_preferences(self, sample_pois):
        selector = POISelector()
        result = selector.select(sample_pois, preferences=["historic", "natural"])
        assert all(sp.poi.category in ("historic", "natural") for sp in result)
        assert not any(sp.poi.category == "tourism" for sp in result)

    def test_empty_preferences_all_categories(self, sample_pois):
        selector = POISelector()
        result = selector.select(sample_pois, preferences=[])
        categories = {sp.poi.category for sp in result}
        assert len(categories) > 1

    def test_preference_case_insensitive(self, sample_pois):
        selector = POISelector()
        result = selector.select(sample_pois, preferences=["HISTORIC"])
        assert all(sp.poi.category == "historic" for sp in result)

    def test_no_match_falls_back_to_all(self, sample_pois):
        selector = POISelector()
        result = selector.select(sample_pois, preferences=["vineyard"])
        # should return results from all categories (fallback)
        assert len(result) > 0
        categories = {sp.poi.category for sp in result}
        assert len(categories) > 1

    def test_empty_input_returns_empty(self):
        selector = POISelector()
        assert selector.select([], preferences=[]) == []

    def test_geographic_spread_prevents_clustering(self):
        # 4 POIs clustered within 1 km of each other, 1 POI 5 km away.
        # With top_n=2, the selector should pick at most 1 from the cluster
        # and the distant one rather than 2 from the cluster.
        clustered = [
            _scored("Monument A", "historic", 0.0, 0.0, lat=37.780, lon=-122.410),
            _scored("Monument B", "historic", 0.1, 0.1, lat=37.782, lon=-122.411),
            _scored("Monument C", "historic", 0.2, 0.2, lat=37.783, lon=-122.412),
        ]
        distant = _scored("Golden Gate Bridge", "tourism", 0.3, 0.3, lat=37.820, lon=-122.478)
        selector = POISelector(top_n=2)
        result = selector.select(clustered + [distant], preferences=[])
        assert len(result) == 2
        names = {sp.poi.name for sp in result}
        assert "Golden Gate Bridge" in names, "distant POI should be selected over cluster duplicates"
        # Only one from the cluster should appear
        cluster_names = names & {"Monument A", "Monument B", "Monument C"}
        assert len(cluster_names) == 1
