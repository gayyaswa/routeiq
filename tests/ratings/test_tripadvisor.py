"""Tests for TripAdvisorRatingProvider."""
import json
import os
import time
import pytest
from unittest.mock import MagicMock, patch

from routeiq.graph.poi import POI
from routeiq.ratings.tripadvisor import TripAdvisorRatingProvider, _CACHE_TTL_SECONDS

_CITY = "San Francisco, CA"
_SAFE_CITY = "san_francisco_ca"

_POI_ALCATRAZ = POI(
    name="Alcatraz Island",
    category="tourism",
    lat=37.8267,
    lon=-122.4233,
    osm_id="way/123",
    wikipedia_tag="en:Alcatraz_Island",
)
_POI_COIT = POI(
    name="Coit Tower",
    category="tourism",
    lat=37.8024,
    lon=-122.4058,
    osm_id="way/456",
)

_POOL_ITEM = {
    "location_id": "321",
    "name": "Alcatraz Island",
    "latitude": "37.8267",
    "longitude": "-122.4233",
    "rating": "4.5",
    "num_reviews": "5000",
}

_REVIEWS_DATA = [
    {"text": "Amazing experience! The history is absolutely mind-blowing and the bay views are simply spectacular."},
    {"text": "A must-visit destination! The audio tour is excellent and very informative for visitors of all ages."},
    {"text": "One of the finest historic sites I have ever visited in all my travels. Book tickets well ahead!"},
    {"text": "Ok."},                # 3 chars — filtered by _MIN_REVIEW_CHARS (< 80)
]

_PHOTOS_DATA = [
    {"images": {"large": {"url": "https://example.com/photo1.jpg"}, "medium": {"url": "https://example.com/photo1m.jpg"}}},
    {"images": {"large": {"url": "https://example.com/photo2.jpg"}}},
    {"images": {"medium": {"url": "https://example.com/photo3m.jpg"}}},  # no large → medium fallback
    {"images": {"large": {"url": "https://example.com/photo4.jpg"}}},
    {"images": {"large": {"url": "https://example.com/photo5.jpg"}}},
]


def _nearby_resp(data):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"data": data}
    return m


def _reviews_resp():
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"data": _REVIEWS_DATA}
    return m


def _photos_resp():
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {"data": _PHOTOS_DATA}
    return m


@pytest.fixture
def provider(tmp_path):
    return TripAdvisorRatingProvider(api_key="test-key", cache_dir=str(tmp_path))


def _setup_all_calls(nearby_data=None):
    """Return a side_effect list: nearby → reviews → photos."""
    if nearby_data is None:
        nearby_data = [_POOL_ITEM]

    def side_effect(url, **kwargs):
        if "nearby_search" in url:
            return _nearby_resp(nearby_data)
        if "/reviews" in url:
            return _reviews_resp()
        if "/photos" in url:
            return _photos_resp()
        raise ValueError(f"Unexpected URL: {url}")

    return side_effect


class TestPoolCache:
    def test_cache_miss_calls_api_and_writes_file(self, provider, tmp_path):
        with patch("requests.get", side_effect=_setup_all_calls()):
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        pool_file = tmp_path / f"tripadvisor_{_SAFE_CITY}_pool.json"
        assert pool_file.exists()
        assert json.loads(pool_file.read_text()) == [_POOL_ITEM]

    def test_cache_hit_skips_nearby_api(self, provider, tmp_path):
        # Pre-seed pool cache
        pool_file = tmp_path / f"tripadvisor_{_SAFE_CITY}_pool.json"
        pool_file.write_text(json.dumps([_POOL_ITEM]))

        with patch("requests.get", side_effect=_setup_all_calls()) as mock_get:
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        # nearby_search must NOT be called; reviews+photos may still be called
        nearby_calls = [c for c in mock_get.call_args_list if "nearby_search" in c.args[0]]
        assert len(nearby_calls) == 0

    def test_stale_pool_cache_triggers_api(self, provider, tmp_path):
        pool_file = tmp_path / f"tripadvisor_{_SAFE_CITY}_pool.json"
        pool_file.write_text(json.dumps([_POOL_ITEM]))
        old_mtime = time.time() - _CACHE_TTL_SECONDS - 1
        os.utime(pool_file, (old_mtime, old_mtime))

        with patch("requests.get", side_effect=_setup_all_calls()) as mock_get:
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        nearby_calls = [c for c in mock_get.call_args_list if "nearby_search" in c.args[0]]
        assert len(nearby_calls) == 1


class TestReviewsCache:
    def test_reviews_cached_per_location_id(self, provider, tmp_path):
        with patch("requests.get", side_effect=_setup_all_calls()):
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        review_file = tmp_path / "tripadvisor_review_321.json"
        assert review_file.exists()

    def test_reviews_cache_hit_skips_api(self, provider, tmp_path):
        # Pre-seed pool + review caches
        (tmp_path / f"tripadvisor_{_SAFE_CITY}_pool.json").write_text(json.dumps([_POOL_ITEM]))
        (tmp_path / "tripadvisor_review_321.json").write_text(json.dumps(["cached review"]))

        with patch("requests.get", side_effect=_setup_all_calls()) as mock_get:
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        review_calls = [c for c in mock_get.call_args_list if "/reviews" in c.args[0]]
        assert len(review_calls) == 0
        assert rated[0].review_snippet == "cached review"


class TestPhotosCache:
    def test_photos_cached_per_location_id(self, provider, tmp_path):
        with patch("requests.get", side_effect=_setup_all_calls()):
            provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        photos_file = tmp_path / "tripadvisor_photos_321.json"
        assert photos_file.exists()

    def test_photo_url_large_fallback_to_medium(self, provider, tmp_path):
        # Photo 3 has no large → should fall back to medium
        with patch("requests.get", side_effect=_setup_all_calls()):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        urls = rated[0].photo_urls or []
        assert "https://example.com/photo3m.jpg" in urls


class TestRatingPassthrough:
    def test_rating_not_divided_by_two(self, provider):
        # TripAdvisor is already 1–5 — no ÷2 normalization
        with patch("requests.get", side_effect=_setup_all_calls()):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating == pytest.approx(4.5)

    def test_missing_rating_is_none(self, provider):
        no_rating = {**_POOL_ITEM, "rating": ""}
        with patch("requests.get", side_effect=_setup_all_calls([no_rating])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating is None


class TestSnippetsAndPhotos:
    def test_all_snippets_filters_short_reviews(self, provider):
        # _REVIEWS_DATA has 4 items; last one is < 80 chars → filtered
        with patch("requests.get", side_effect=_setup_all_calls()):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        snippets = rated[0].all_snippets or []
        assert len(snippets) == 3
        assert all(len(s) >= 80 for s in snippets)

    def test_photo_urls_max_five(self, provider):
        with patch("requests.get", side_effect=_setup_all_calls()):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert len(rated[0].photo_urls or []) <= 5


class TestReviewSource:
    def test_review_source_always_tripadvisor_on_match(self, provider):
        with patch("requests.get", side_effect=_setup_all_calls()):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].review_source == "TripAdvisor"

    def test_review_source_set_on_empty_pool(self, provider):
        with patch("requests.get", side_effect=_setup_all_calls([])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].review_source == "TripAdvisor"
        assert rated[0].rating is None


class TestNameMatchAndProximity:
    def test_name_similarity_match(self, provider):
        # "Alcatraz Island" (OSM) vs "Alcatraz Island" (TA) — direct name match
        with patch("requests.get", side_effect=_setup_all_calls()):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating is not None

    def test_proximity_fallback_within_100m(self, provider):
        # Name differs but coordinates match within 100 m
        nearby = {**_POOL_ITEM, "name": "ZYXWVU_Totally_Different_Name",
                  "latitude": "37.8267", "longitude": "-122.4233"}
        with patch("requests.get", side_effect=_setup_all_calls([nearby])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating == pytest.approx(4.5)

    def test_no_match_returns_null_fields(self, provider):
        far = {**_POOL_ITEM, "name": "ZYXWVU_Totally_Different",
               "latitude": "34.0", "longitude": "-118.0"}   # Los Angeles
        with patch("requests.get", side_effect=_setup_all_calls([far])):
            rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])

        assert rated[0].rating is None
