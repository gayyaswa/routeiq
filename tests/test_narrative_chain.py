import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from routeiq.graph import POI
from routeiq.routing import ScoredPOI
from routeiq.insights import NarrativeChain
from routeiq.insights.prompts import NARRATIVE_PROMPT

_NARRATIVE = "A beautiful scenic drive through Texas Hill Country awaits you..."


@pytest.fixture
def mock_llm():
    return RunnableLambda(lambda msgs: AIMessage(content=_NARRATIVE))


@pytest.fixture
def chain(mock_llm):
    return NarrativeChain(NARRATIVE_PROMPT, mock_llm)


@pytest.fixture
def sample_top_pois():
    poi1 = POI(name="San Jose Mission", category="historic", lat=29.36, lon=-98.46, osm_id="1")
    poi2 = POI(name="Natural Bridge Caverns", category="tourism", lat=29.69, lon=-98.35, osm_id="2")
    return [
        ScoredPOI(poi=poi1, detour_km=2.1, detour_min=2.5),
        ScoredPOI(poi=poi2, detour_km=4.8, detour_min=5.8),
    ]


class TestNarrativeChainGenerate:
    def test_returns_string(self, chain, sample_top_pois):
        result = chain.generate("Austin, TX", "San Antonio, TX", 120.0, 144.0, sample_top_pois)
        assert isinstance(result, str)

    def test_narrative_not_empty(self, chain, sample_top_pois):
        result = chain.generate("Austin, TX", "San Antonio, TX", 120.0, 144.0, sample_top_pois)
        assert len(result) > 0


class TestNarrativeChainFormatPOIContext:
    def test_empty_pois_returns_no_stops_message(self):
        context = NarrativeChain._format_poi_context([])
        assert "No scenic stops" in context

    def test_poi_name_in_context(self, sample_top_pois):
        context = NarrativeChain._format_poi_context(sample_top_pois)
        assert "San Jose Mission" in context

    def test_poi_category_in_context(self, sample_top_pois):
        context = NarrativeChain._format_poi_context(sample_top_pois)
        assert "(historic)" in context

    def test_detour_time_in_context(self, sample_top_pois):
        context = NarrativeChain._format_poi_context(sample_top_pois)
        assert "2 min" in context or "3 min" in context  # 2.5 rounds to 2 or 3
