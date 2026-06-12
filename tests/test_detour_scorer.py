import math
import pytest

from routeiq.graph import POI
from routeiq.routing import DetourScorer, ScoredPOI

# Austin City Hall
AUSTIN_LAT, AUSTIN_LON = 30.267, -97.743
# San Antonio City Hall
SA_LAT, SA_LON = 29.424, -98.495

ROUTE = [
    (29.5, -98.0),
    (29.55, -98.0),
    (29.6, -98.0),
]

def _poi(lat, lon, name="Test POI", category="historic"):
    return POI(name=name, category=category, lat=lat, lon=lon, osm_id="1")


class TestDetourScorerScore:
    def test_empty_pois_returns_empty(self):
        scorer = DetourScorer()
        assert scorer.score([], ROUTE) == []

    def test_empty_route_returns_empty(self):
        scorer = DetourScorer()
        assert scorer.score([_poi(29.55, -98.0)], []) == []

    def test_poi_on_route_has_near_zero_detour(self):
        scorer = DetourScorer()
        poi = _poi(29.55, -98.0)  # exact midpoint of ROUTE
        result = scorer.score([poi], ROUTE)
        assert result[0].detour_km == pytest.approx(0.0, abs=0.01)

    def test_detour_km_is_double_nearest_dist(self):
        scorer = DetourScorer()
        poi = _poi(29.55, -97.98)
        expected_one_way = DetourScorer._haversine_km(29.55, -97.98, 29.55, -98.0)
        result = scorer.score([poi], ROUTE)
        assert result[0].detour_km == pytest.approx(2.0 * expected_one_way, rel=1e-5)

    def test_detour_min_derived_from_km(self):
        scorer = DetourScorer(avg_speed_kmh=50.0)
        poi = _poi(29.55, -97.9)
        result = scorer.score([poi], ROUTE)
        sp = result[0]
        assert sp.detour_min == pytest.approx(sp.detour_km / 50.0 * 60.0, rel=1e-9)

    def test_returns_scored_poi_instances(self):
        scorer = DetourScorer()
        result = scorer.score([_poi(29.55, -98.0)], ROUTE)
        assert isinstance(result[0], ScoredPOI)

    def test_all_pois_scored(self):
        scorer = DetourScorer()
        pois = [_poi(29.5, -98.0), _poi(29.55, -98.0), _poi(29.6, -98.0)]
        result = scorer.score(pois, ROUTE)
        assert len(result) == 3


class TestDetourScorerHaversine:
    def test_same_point_is_zero(self):
        assert DetourScorer._haversine_km(30.0, -97.0, 30.0, -97.0) == pytest.approx(0.0, abs=1e-9)

    def test_known_distance_austin_to_sa(self):
        dist = DetourScorer._haversine_km(AUSTIN_LAT, AUSTIN_LON, SA_LAT, SA_LON)
        assert dist == pytest.approx(118.5, abs=1.0)

    def test_symmetry(self):
        d1 = DetourScorer._haversine_km(30.0, -97.0, 29.5, -98.0)
        d2 = DetourScorer._haversine_km(29.5, -98.0, 30.0, -97.0)
        assert d1 == pytest.approx(d2, rel=1e-9)
