"""Tests for TavilyActivityClassifier — mocked Tavily + LLM, no real API calls."""
from __future__ import annotations
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from routeiq.graph.poi import POI


def _poi(name, osm_id, subtype=None, category="tourism"):
    return POI(name=name, category=category, lat=0.0, lon=0.0, osm_id=osm_id, subtype=subtype)


@pytest.fixture
def mock_tavily():
    """Patch tavily.TavilyClient at the source so __init__ gets the mock."""
    with patch("tavily.TavilyClient") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def classifier(mock_tavily, mock_llm, tmp_path):
    from routeiq.activities.tavily_classifier import TavilyActivityClassifier
    return TavilyActivityClassifier(
        api_key="fake-key",
        llm=mock_llm,
        cache_dir=str(tmp_path / "cache"),
    )


class TestMatchedPOI:
    def test_matched_poi_gets_activity(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.return_value = {
            "results": [{"title": "Lakeside Trail", "content": "Great hiking trail near the lake"}]
        }
        mock_llm.invoke.return_value = MagicMock(content='["Trail Head"]')
        pois = [_poi("Trail Head", "1"), _poi("City Museum", "2")]
        results = classifier.classify_batch("TestCity", pois, ["hiking"])
        by_id = {r.poi.osm_id: r for r in results}
        assert "hiking" in by_id["1"].matched_activities
        assert "hiking" not in by_id["2"].matched_activities

    def test_evidence_set_on_match(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.return_value = {
            "results": [{"title": "HQ Trail", "content": "Best hiking spot with trails and views " * 5}]
        }
        mock_llm.invoke.return_value = MagicMock(content='["Trail HQ"]')
        results = classifier.classify_batch("City", [_poi("Trail HQ", "1")], ["hiking"])
        assert results[0].activity_evidence is not None
        assert "Tavily" in results[0].activity_evidence


class TestCacheBehaviour:
    def test_cache_hit_skips_api(self, classifier, mock_tavily, mock_llm, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_path = cache_dir / "tavily_classify_testcity_hiking.json"
        cache_path.write_text(json.dumps([{"title": "Cached Trail", "content": "Great hike"}]))
        mock_llm.invoke.return_value = MagicMock(content="[]")
        classifier.classify_batch("TestCity", [_poi("Spot", "1")], ["hiking"])
        mock_tavily.search.assert_not_called()

    def test_cache_miss_calls_api(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.return_value = {"results": []}
        mock_llm.invoke.return_value = MagicMock(content="[]")
        classifier.classify_batch("NewCity", [_poi("Spot", "1")], ["hiking"])
        mock_tavily.search.assert_called_once()


class TestEmptyAndFallback:
    def test_empty_results_gives_untagged(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.return_value = {"results": []}
        results = classifier.classify_batch("EmptyCity", [_poi("Museum", "1")], ["hiking"])
        assert results[0].matched_activities == []

    def test_all_pois_returned_including_unmatched(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.return_value = {"results": [{"title": "x", "content": "y"}]}
        mock_llm.invoke.return_value = MagicMock(content="[]")
        pois = [_poi("A", "1"), _poi("B", "2")]
        results = classifier.classify_batch("City", pois, ["hiking"])
        assert len(results) == 2

    def test_llm_parse_error_returns_no_match(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.return_value = {
            "results": [{"title": "Trail", "content": "some hiking content here"}]
        }
        mock_llm.invoke.return_value = MagicMock(content="not json at all")
        results = classifier.classify_batch("City", [_poi("Trail", "1")], ["hiking"])
        assert results[0].matched_activities == []

    def test_api_exception_returns_untagged(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.side_effect = RuntimeError("API down")
        results = classifier.classify_batch("City", [_poi("Spot", "1")], ["hiking"])
        assert results[0].matched_activities == []

    def test_empty_pois_returns_empty(self, classifier, mock_tavily):
        # classify_batch still calls _fetch (activity loop runs before POI check),
        # so we need a valid mock return value to avoid JSON serialisation error.
        mock_tavily.search.return_value = {"results": []}
        results = classifier.classify_batch("City", [], ["hiking"])
        assert results == []

    def test_multiple_activities_searched_separately(self, classifier, mock_tavily, mock_llm):
        mock_tavily.search.return_value = {"results": []}
        mock_llm.invoke.return_value = MagicMock(content="[]")
        classifier.classify_batch("City", [_poi("Spot", "1")], ["hiking", "biking"])
        assert mock_tavily.search.call_count == 2
