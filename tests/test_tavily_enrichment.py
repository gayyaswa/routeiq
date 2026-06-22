"""Tests for TavilyEnrichmentProvider — mocked Tavily + LLM, no real API calls."""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch

from routeiq.graph.poi import POI


def _poi(name, osm_id, category="tourism"):
    return POI(name=name, category=category, lat=37.8, lon=-122.4, osm_id=osm_id)


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_llm():
    m = MagicMock()
    m.invoke.return_value = MagicMock(
        content='{"visitor_quote": "Amazing place!", "highlights": ["views", "history", "access"]}'
    )
    return m


@pytest.fixture
def provider(mock_client, mock_llm, tmp_path):
    with patch("tavily.TavilyClient", return_value=mock_client):
        from routeiq.ratings.tavily_enrichment import TavilyEnrichmentProvider
        return TavilyEnrichmentProvider(
            api_key="fake-key",
            llm=mock_llm,
            cache_dir=str(tmp_path / "cache"),
        )


class TestBulkFetch:
    def test_bulk_hit_used_when_poi_name_in_results(self, provider, mock_client, mock_llm):
        poi = _poi("Golden Gate Bridge", "1")
        mock_client.search.return_value = {"results": [
            {"title": "Golden Gate Bridge Tours", "content": "amazing golden gate bridge visit"},
            {"title": "SF Guide", "content": "golden gate bridge iconic attraction"},
        ]}
        provider.enrich_batch("San Francisco, CA", [poi])
        # Only one search call for bulk — no per-POI fallback
        assert mock_client.search.call_count == 1

    def test_per_poi_fallback_when_name_not_in_bulk(self, provider, mock_client, mock_llm):
        poi = _poi("Hidden Gem Cave", "1")
        bulk_results = [{"title": "SF Attractions", "content": "visit fishermans wharf"}]
        per_poi_results = [{"title": "Hidden Gem Cave Guide", "content": "a wonderful cave experience"}]
        mock_client.search.side_effect = [
            {"results": bulk_results},
            {"results": per_poi_results},
        ]
        provider.enrich_batch("San Francisco, CA", [poi])
        assert mock_client.search.call_count == 2

    def test_cache_hit_skips_bulk_api(self, provider, mock_client, mock_llm, tmp_path):
        cache_file = tmp_path / "cache" / "tavily_enrich_san_francisco_ca.json"
        cache_file.write_text(json.dumps([
            {"title": "Alcatraz Tours", "content": "alcatraz island historic prison visit experience"}
        ]))
        poi = _poi("Alcatraz", "1")
        mock_client.search.return_value = {"results": []}  # per-POI fallback
        provider.enrich_batch("San Francisco, CA", [poi])
        # No bulk search since cache exists; only per-POI fallback may fire
        bulk_calls = [c for c in mock_client.search.call_args_list
                      if "attractions" in str(c) or "highlights" in str(c) or "best" in str(c)]
        assert len(bulk_calls) == 0


class TestRatedPOIFields:
    def test_review_source_is_tavily(self, provider, mock_client):
        poi = _poi("Alcatraz", "1")
        mock_client.search.return_value = {"results": []}
        results = provider.enrich_batch("SF", [poi])
        assert results[0].review_source == "Tavily"

    def test_fields_populated_from_llm_extraction(self, provider, mock_client, mock_llm):
        poi = _poi("Alcatraz", "1")
        mock_client.search.return_value = {"results": [
            {"title": "Alcatraz Tour", "content": "alcatraz is a must-see historic prison"},
            {"title": "Alcatraz Visit", "content": "alcatraz prison island famous attraction"},
        ]}
        mock_llm.invoke.return_value = MagicMock(
            content='{"visitor_quote": "A must-visit", "highlights": ["audio tour", "bay views", "history"]}'
        )
        results = provider.enrich_batch("SF", [poi])
        rated = results[0]
        assert rated.review_snippet == "A must-visit"
        assert rated.all_snippets == ["audio tour", "bay views", "history"]

    def test_poi_object_preserved(self, provider, mock_client):
        poi = _poi("Alcatraz", "1")
        mock_client.search.return_value = {"results": []}
        results = provider.enrich_batch("SF", [poi])
        assert results[0].poi is poi


class TestEdgeCases:
    def test_empty_pois_returns_empty(self, provider):
        assert provider.enrich_batch("SF", []) == []

    def test_no_match_returns_rated_poi_with_source(self, provider, mock_client):
        poi = _poi("Unknown XYZ", "1")
        mock_client.search.return_value = {"results": []}
        results = provider.enrich_batch("SF", [poi])
        rated = results[0]
        assert rated.poi == poi
        assert rated.review_source == "Tavily"
        assert rated.review_snippet is None

    def test_multiple_pois_all_returned(self, provider, mock_client):
        pois = [_poi("Alcatraz", "1"), _poi("Golden Gate", "2")]
        mock_client.search.return_value = {"results": []}
        results = provider.enrich_batch("SF", pois)
        assert len(results) == 2

    def test_api_exception_returns_minimal_rated_poi(self, provider, mock_client):
        poi = _poi("Spot", "1")
        mock_client.search.side_effect = RuntimeError("API down")
        results = provider.enrich_batch("SF", [poi])
        assert len(results) == 1
        assert results[0].review_source == "Tavily"
        assert results[0].review_snippet is None

    def test_source_name_property(self, provider):
        assert provider.source_name == "Tavily"

    def test_photo_url_extracted_when_present(self, provider, mock_client, mock_llm):
        poi = _poi("Park", "1")
        mock_client.search.return_value = {"results": [
            {"title": "Park visit", "content": "park visit experience",
             "url": "https://example.com/park.jpg"},
            {"title": "Park review", "content": "beautiful park visit review"},
        ]}
        results = provider.enrich_batch("SF", [poi])
        rated = results[0]
        assert rated.photo_urls == ["https://example.com/park.jpg"]
