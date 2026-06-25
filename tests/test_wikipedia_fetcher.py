"""Unit tests for WikipediaFetcher — all network calls mocked."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from routeiq.graph.poi import POI
import routeiq.rag.wikipedia_fetcher as _wiki_mod
from routeiq.rag.wikipedia_fetcher import WikipediaFetcher, _DESCRIPTION_MAX_CHARS


def _make_poi(**kwargs):
    defaults = dict(name="Enchanted Rock", category="natural", lat=30.5, lon=-98.8, osm_id="r1")
    defaults.update(kwargs)
    return POI(**defaults)


def _mock_session(status=200, json_data=None):
    session = MagicMock(spec=requests.Session)
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or {}
    session.get.return_value = resp
    return session


# ── _resolve_title ─────────────────────────────────────────────────────────

class TestResolveTitle:
    def test_uses_wikipedia_tag_with_lang_prefix(self):
        session = _mock_session()
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag="en:Enchanted Rock")
        title = fetcher._resolve_title(poi)
        assert title == "Enchanted Rock"
        session.get.assert_not_called()  # no network needed

    def test_uses_wikipedia_tag_without_prefix(self):
        session = _mock_session()
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag="Enchanted Rock")
        title = fetcher._resolve_title(poi)
        assert title == "Enchanted Rock"

    def test_falls_back_to_opensearch_when_no_tag(self):
        session = _mock_session(json_data=["Enchanted Rock", ["Enchanted Rock State Natural Area"], [], []])
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag=None)
        title = fetcher._resolve_title(poi)
        assert title == "Enchanted Rock State Natural Area"
        session.get.assert_called_once()

    def test_returns_none_when_opensearch_empty(self):
        session = _mock_session(json_data=["query", [], [], []])
        fetcher = WikipediaFetcher(session=session)
        title = fetcher._resolve_title(_make_poi(wikipedia_tag=None))
        assert title is None

    def test_returns_none_on_network_error(self):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.ConnectionError("timeout")
        fetcher = WikipediaFetcher(session=session)
        title = fetcher._resolve_title(_make_poi(wikipedia_tag=None))
        assert title is None


# ── enrich ─────────────────────────────────────────────────────────────────

class TestEnrich:
    def setup_method(self):
        # Reset the module-level cache so mocked sessions aren't bypassed by real cached data.
        _wiki_mod._cache = {}
    def test_sets_description_and_image_url(self):
        summary_data = {
            "extract": "Enchanted Rock is a giant pink granite dome rising 425 feet above the surrounding terrain.",
            "thumbnail": {"source": "https://upload.wikimedia.org/wikipedia/commons/thumb/enchanted.jpg"},
        }
        session = _mock_session(json_data=summary_data)
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag="en:Enchanted Rock")
        fetcher.enrich(poi)
        assert poi.description is not None
        assert "granite" in poi.description
        assert poi.image_url == "https://upload.wikimedia.org/wikipedia/commons/thumb/enchanted.jpg"

    def test_truncates_long_extract(self):
        long_extract = "A" * (_DESCRIPTION_MAX_CHARS + 200)
        session = _mock_session(json_data={"extract": long_extract})
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag="en:SomePlace")
        fetcher.enrich(poi)
        assert len(poi.description) == _DESCRIPTION_MAX_CHARS

    def test_no_description_when_no_title_resolved(self):
        session = _mock_session(json_data=["q", [], [], []])
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag=None)
        fetcher.enrich(poi)
        assert poi.description is None
        assert poi.image_url is None

    def test_graceful_on_non_200_response(self):
        session = _mock_session(status=404, json_data={})
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag="en:Nonexistent")
        fetcher.enrich(poi)
        assert poi.description is None

    def test_graceful_on_network_exception(self):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.ConnectionError("offline")
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag="en:SomePage")
        fetcher.enrich(poi)
        assert poi.description is None

    def test_image_url_skipped_when_no_thumbnail(self):
        session = _mock_session(json_data={"extract": "Some text.", "thumbnail": {}})
        fetcher = WikipediaFetcher(session=session)
        poi = _make_poi(wikipedia_tag="en:SomePage")
        fetcher.enrich(poi)
        assert poi.description == "Some text."
        assert poi.image_url is None
