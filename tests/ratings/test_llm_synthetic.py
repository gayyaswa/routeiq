"""Tests for LLMSyntheticRatingProvider."""
import json
import os
import time
import pytest
from unittest.mock import MagicMock, patch

from routeiq.graph.poi import POI
from routeiq.ratings.llm_synthetic import LLMSyntheticRatingProvider, _CACHE_TTL_SECONDS

_CITY = "San Francisco, CA"
_SAFE_CITY = "san_francisco_ca"

_POI_ALCATRAZ = POI(
    name="Alcatraz Island",
    category="tourism",
    lat=37.8267,
    lon=-122.4233,
    osm_id="way/123",
    description="Historic federal penitentiary island in San Francisco Bay.",
)
_POI_COIT = POI(
    name="Coit Tower",
    category="tourism",
    lat=37.8024,
    lon=-122.4058,
    osm_id="way/456",
)

_LLM_RESPONSE = [
    {
        "name": "Alcatraz Island",
        "rating": 4.7,
        "review_count": 9200,
        "snippets": [
            "The audio tour brought the prison's dark history to life — absolutely haunting.",
            "Stunning views of the bay from the island; book tickets weeks in advance.",
        ],
        "hours": "Daily 8:30 AM – 6:30 PM",
    },
    {
        "name": "Coit Tower",
        "rating": 4.3,
        "review_count": 1800,
        "snippets": [
            "The murals inside are stunning and the panoramic views from the top are worth it.",
        ],
        "hours": "Daily 10:00 AM – 5:00 PM",
    },
]


def _make_llm_response(data):
    m = MagicMock()
    m.content = json.dumps(data)
    return m


@pytest.fixture
def provider(tmp_path):
    p = LLMSyntheticRatingProvider(cache_dir=str(tmp_path))
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = _make_llm_response(_LLM_RESPONSE)
    p._llm = mock_llm
    return p


class TestEnrichBatch:
    def test_returns_one_rated_poi_per_input(self, provider):
        pois = [_POI_ALCATRAZ, _POI_COIT]
        rated = provider.enrich_batch(_CITY, pois)
        assert len(rated) == 2

    def test_source_name_is_ai_insights(self, provider):
        rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert rated[0].review_source == "AI Insights"

    def test_rating_and_count_populated(self, provider):
        rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert rated[0].rating == pytest.approx(4.7)
        assert rated[0].review_count == 9200

    def test_snippets_populated(self, provider):
        rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert len(rated[0].all_snippets or []) == 2
        assert rated[0].review_snippet is not None

    def test_hours_populated(self, provider):
        rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert rated[0].hours == "Daily 8:30 AM – 6:30 PM"

    def test_empty_input_returns_empty(self, provider):
        assert provider.enrich_batch(_CITY, []) == []

    def test_unmatched_poi_gets_null_fields(self, provider, tmp_path):
        unlisted = POI(name="Unknown Spot XYZ", category="tourism",
                       lat=0.0, lon=0.0, osm_id="way/999")
        rated = provider.enrich_batch(_CITY, [unlisted])
        assert rated[0].rating is None
        assert rated[0].review_count is None
        assert rated[0].review_source == "AI Insights"


class TestCaching:
    def test_cache_written_on_first_call(self, provider, tmp_path):
        provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        cache_file = tmp_path / f"llm_synthetic_{_SAFE_CITY}.json"
        assert cache_file.exists()

    def test_cache_hit_skips_llm(self, provider, tmp_path):
        # Pre-seed cache
        cache_file = tmp_path / f"llm_synthetic_{_SAFE_CITY}.json"
        cache_file.write_text(json.dumps(_LLM_RESPONSE))

        provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert provider._llm.invoke.call_count == 0

    def test_stale_cache_triggers_llm(self, provider, tmp_path):
        cache_file = tmp_path / f"llm_synthetic_{_SAFE_CITY}.json"
        cache_file.write_text(json.dumps(_LLM_RESPONSE))
        old_mtime = time.time() - _CACHE_TTL_SECONDS - 1
        os.utime(cache_file, (old_mtime, old_mtime))

        provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert provider._llm.invoke.call_count == 1

    def test_missing_pois_added_to_existing_cache(self, provider, tmp_path):
        # Seed cache with only Alcatraz
        cache_file = tmp_path / f"llm_synthetic_{_SAFE_CITY}.json"
        cache_file.write_text(json.dumps([_LLM_RESPONSE[0]]))

        # Request both — Coit Tower is missing, should trigger LLM for it only
        provider.enrich_batch(_CITY, [_POI_ALCATRAZ, _POI_COIT])
        assert provider._llm.invoke.call_count == 1
        # Both should now be in the cache
        merged = json.loads(cache_file.read_text())
        names = {item["name"] for item in merged}
        assert "Alcatraz Island" in names
        assert "Coit Tower" in names


class TestLLMFailure:
    def test_llm_error_returns_null_fields(self, tmp_path):
        provider = LLMSyntheticRatingProvider(cache_dir=str(tmp_path))
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM unavailable")
        provider._llm = mock_llm

        rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert len(rated) == 1
        assert rated[0].rating is None

    def test_llm_invalid_json_returns_null_fields(self, tmp_path):
        provider = LLMSyntheticRatingProvider(cache_dir=str(tmp_path))
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="not valid json at all")
        provider._llm = mock_llm

        rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert rated[0].rating is None

    def test_llm_markdown_fences_stripped(self, tmp_path):
        provider = LLMSyntheticRatingProvider(cache_dir=str(tmp_path))
        mock_llm = MagicMock()
        fenced = f"```json\n{json.dumps(_LLM_RESPONSE)}\n```"
        mock_llm.invoke.return_value = MagicMock(content=fenced)
        provider._llm = mock_llm

        rated = provider.enrich_batch(_CITY, [_POI_ALCATRAZ])
        assert rated[0].rating == pytest.approx(4.7)
