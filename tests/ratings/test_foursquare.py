import json
import os
import time
import pytest
from unittest.mock import MagicMock, patch

from routeiq.graph.poi import POI
from routeiq.ratings.foursquare import FoursquareRatingProvider, _CACHE_TTL_SECONDS


_CITY = "San Francisco, CA"
_SAFE_CITY = "san_francisco_ca"

_POI_ALCATRAZ = POI(
    name="Alcatraz Island",
    category="tourism",
    lat=37.8267,
    lon=-122.4233,
    osm_id="way/123",
)
_POI_COIT = POI(
    name="Coit Tower",
    category="tourism",
    lat=37.8024,
    lon=-122.4058,
    osm_id="way/456",
)

_FS_RESULT = {
    "name": "Alcatraz",
    "rating": 9.0,
    "stats": {"total_ratings": 5000, "total_tips": 200},
    "tips": [{"text": "Amazing historic site."}],
    "hours": {"display": ["Mon-Sun 9am-5pm"]},
    "geocodes": {"main": {"latitude": 37.8268, "longitude": -122.4234}},
}


def _make_api_response(results):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": results}
    return mock_resp


@pytest.fixture
def provider(tmp_path):
    return FoursquareRatingProvider(api_key="test-key", cache_dir=str(tmp_path))


class TestCacheHitAndMiss:
    def test_cache_miss_calls_api_and_writes_file(self, provider, tmp_path):
        with patch("requests.get", return_value=_make_api_response([_FS_RESULT])) as mock_get:
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        # 3 category buckets → 3 API calls
        assert mock_get.call_count == 3
        cache_files = list(tmp_path.glob(f"foursquare_{_SAFE_CITY}_*.json"))
        assert len(cache_files) == 3

    def test_cache_hit_skips_api(self, provider, tmp_path):
        # Pre-seed fresh cache files for all 3 buckets
        for bucket in ("sights", "arts", "historic"):
            cache_path = tmp_path / f"foursquare_{_SAFE_CITY}_{bucket}.json"
            cache_path.write_text(json.dumps([_FS_RESULT]))

        with patch("requests.get") as mock_get:
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        mock_get.assert_not_called()

    def test_stale_cache_triggers_api(self, provider, tmp_path):
        bucket = "sights"
        cache_path = tmp_path / f"foursquare_{_SAFE_CITY}_{bucket}.json"
        cache_path.write_text(json.dumps([_FS_RESULT]))
        # Force mtime to be older than TTL
        old_mtime = time.time() - _CACHE_TTL_SECONDS - 1
        os.utime(cache_path, (old_mtime, old_mtime))

        with patch("requests.get", return_value=_make_api_response([_FS_RESULT])) as mock_get:
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert mock_get.call_count >= 1


class TestRatingNormalization:
    def test_rating_divided_by_two(self, provider):
        with patch("requests.get", return_value=_make_api_response([_FS_RESULT])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating == pytest.approx(4.5)  # 9.0 / 2

    def test_missing_rating_is_none(self, provider):
        no_rating = {**_FS_RESULT, "rating": None}
        with patch("requests.get", return_value=_make_api_response([no_rating])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating is None

    def test_review_count_from_total_ratings(self, provider):
        with patch("requests.get", return_value=_make_api_response([_FS_RESULT])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].review_count == 5000

    def test_review_count_falls_back_to_total_tips(self, provider):
        no_ratings_stat = {**_FS_RESULT, "stats": {"total_tips": 200}}
        with patch("requests.get", return_value=_make_api_response([no_ratings_stat])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].review_count == 200


class TestNameSimilarityMerge:
    def test_similar_name_matches(self, provider):
        # "Alcatraz Island" (OSM) vs "Alcatraz" (Foursquare) — should match via ChromaDB
        with patch("requests.get", return_value=_make_api_response([_FS_RESULT])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating is not None, "Expected a name-similarity match for Alcatraz Island → Alcatraz"

    def test_no_match_returns_none_quality(self, provider):
        unrelated = {**_FS_RESULT, "name": "Completely Unrelated Place XYZ123",
                     "geocodes": {"main": {"latitude": 0.0, "longitude": 0.0}}}
        with patch("requests.get", return_value=_make_api_response([unrelated])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating is None

    def test_empty_foursquare_pool_passes_through(self, provider):
        with patch("requests.get", return_value=_make_api_response([])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ, _POI_COIT])

        assert all(r.rating is None for r in rated)
        assert [r.poi for r in rated] == [_POI_ALCATRAZ, _POI_COIT]


class TestProximityFallback:
    def test_proximity_match_within_100m(self, provider):
        # Name is very different but geocode is right next to the OSM POI
        nearby = {
            "name": "ZYXWVU Unrelated Name",
            "rating": 7.0,
            "stats": {"total_ratings": 100},
            "tips": [],
            "hours": {},
            # 0.001° ≈ 100 m from _POI_ALCATRAZ
            "geocodes": {"main": {"latitude": 37.8267, "longitude": -122.4233}},
        }
        with patch("requests.get", return_value=_make_api_response([nearby])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating == pytest.approx(3.5)  # 7.0 / 2

    def test_proximity_too_far_returns_none(self, provider):
        far_away = {
            "name": "ZYXWVU Unrelated Name",
            "rating": 7.0,
            "stats": {},
            "tips": [],
            "hours": {},
            "geocodes": {"main": {"latitude": 34.0, "longitude": -118.0}},  # Los Angeles
        }
        with patch("requests.get", return_value=_make_api_response([far_away])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating is None
