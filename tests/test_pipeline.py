from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from routeiq.graph import POI, RouteResult
from routeiq.routing import ScoredPOI
from routeiq.pipeline import RoutePipeline, PipelineState, _ROUTE_TOO_LONG_MIN


def _make_pipeline(**overrides):
    defaults = dict(
        query_parser=MagicMock(),
        graph_loader=MagicMock(),
        poi_finder=MagicMock(),
        detour_scorer=MagicMock(),
        poi_selector=MagicMock(),
        narrative_chain=MagicMock(),
        fallback_chain=MagicMock(),
    )
    defaults.update(overrides)
    return RoutePipeline(**defaults)


def _base_state(**overrides) -> PipelineState:
    state: PipelineState = {
        "query": "Drive from Austin to San Antonio",
        "origin": None,
        "destination": None,
        "preferences": None,
        "origin_lat": None,
        "origin_lon": None,
        "dest_lat": None,
        "dest_lon": None,
        "route_result": None,
        "pois": None,
        "top_pois": None,
        "poi_context": None,
        "narrative": None,
        "error": None,
        "fallback_reason": None,
    }
    state.update(overrides)
    return state


def _fake_route_result(drive_time_min=144.0, length_km=120.0):
    return RouteResult(
        route_nodes=[0, 1, 2],
        route_coords=[(29.5, -98.0), (29.55, -98.0), (29.6, -98.0)],
        length_km=length_km,
        drive_time_min=drive_time_min,
    )


def _fake_poi():
    return POI(name="Alamo", category="historic", lat=29.42, lon=-98.48, osm_id="1")


def _fake_scored_poi():
    return ScoredPOI(poi=_fake_poi(), detour_km=1.0, detour_min=1.2)


# ── parse node ─────────────────────────────────────────────────────────────

class TestParseNode:
    def test_success_sets_origin_destination_preferences(self):
        p = _make_pipeline()
        p._query_parser.parse.return_value = {
            "origin": "Austin, TX",
            "destination": "San Antonio, TX",
            "preferences": ["historic"],
        }
        result = p._parse_node(_base_state())
        assert result["origin"] == "Austin, TX"
        assert result["destination"] == "San Antonio, TX"
        assert result["preferences"] == ["historic"]
        assert "error" not in result

    def test_parse_error_sets_error_field(self):
        p = _make_pipeline()
        p._query_parser.parse.return_value = {
            "origin": None,
            "destination": None,
            "preferences": [],
            "_parse_error": "JSONDecodeError",
        }
        result = p._parse_node(_base_state())
        assert result["error"] == "unparseable_query"
        assert "fallback_reason" in result


# ── route_after_parse ──────────────────────────────────────────────────────

class TestRouteAfterParse:
    def test_routes_to_graph_on_success(self):
        p = _make_pipeline()
        state = _base_state(origin="Austin, TX", destination="San Antonio, TX")
        assert p._route_after_parse(state) == "graph"

    def test_routes_to_narrate_on_error(self):
        p = _make_pipeline()
        state = _base_state(error="unparseable_query")
        assert p._route_after_parse(state) == "narrate"

    def test_routes_to_narrate_when_origin_missing(self):
        p = _make_pipeline()
        state = _base_state(destination="San Antonio, TX")
        assert p._route_after_parse(state) == "narrate"

    def test_routes_to_narrate_when_destination_missing(self):
        p = _make_pipeline()
        state = _base_state(origin="Austin, TX")
        assert p._route_after_parse(state) == "narrate"


# ── graph node ─────────────────────────────────────────────────────────────

class TestGraphNode:
    def _setup(self, route_result=None, pois=None, top_pois=None):
        p = _make_pipeline()
        p._graph_loader.load.return_value = MagicMock(spec=nx.MultiDiGraph)
        p._poi_finder.find_pois.return_value = pois or [_fake_poi()]
        p._detour_scorer.score.return_value = [_fake_scored_poi()]
        p._poi_selector.select.return_value = top_pois or [_fake_scored_poi()]
        return p

    def test_success_sets_route_result_pois_top_pois(self):
        p = self._setup()
        rr = _fake_route_result()
        with (
            patch("osmnx.geocode", side_effect=[(30.267, -97.743), (29.424, -98.495)]),
            patch("routeiq.pipeline.RouteGraph") as MockRG,
        ):
            MockRG.return_value.find_route.return_value = rr
            result = p._graph_node(_base_state(origin="Austin, TX", destination="San Antonio, TX", preferences=[]))
        assert result["route_result"] is rr
        assert result["pois"] is not None
        assert result["top_pois"] is not None
        assert "error" not in result

    def test_geocode_failure_sets_geocode_failed_error(self):
        p = self._setup()
        with patch("osmnx.geocode", side_effect=Exception("Network error")):
            result = p._graph_node(_base_state(origin="Nowhere", destination="Somewhere", preferences=[]))
        assert result["error"] == "geocode_failed"

    def test_route_not_found_sets_error(self):
        p = self._setup()
        with (
            patch("osmnx.geocode", side_effect=[(30.267, -97.743), (29.424, -98.495)]),
            patch("routeiq.pipeline.RouteGraph") as MockRG,
        ):
            MockRG.return_value.find_route.side_effect = ValueError("No path found")
            result = p._graph_node(_base_state(origin="Austin, TX", destination="San Antonio, TX", preferences=[]))
        assert result["error"] == "route_not_found"

    def test_route_too_long_sets_error(self):
        p = self._setup()
        rr = _fake_route_result(drive_time_min=_ROUTE_TOO_LONG_MIN + 1)
        with (
            patch("osmnx.geocode", side_effect=[(30.267, -97.743), (29.424, -98.495)]),
            patch("routeiq.pipeline.RouteGraph") as MockRG,
        ):
            MockRG.return_value.find_route.return_value = rr
            result = p._graph_node(_base_state(origin="Austin, TX", destination="San Antonio, TX", preferences=[]))
        assert result["error"] == "route_too_long"


# ── route_after_graph ──────────────────────────────────────────────────────

class TestRouteAfterGraph:
    def test_routes_to_rag_on_success(self):
        p = _make_pipeline()
        assert p._route_after_graph(_base_state()) == "rag"

    def test_routes_to_narrate_on_error(self):
        p = _make_pipeline()
        assert p._route_after_graph(_base_state(error="route_not_found")) == "narrate"


# ── rag node ───────────────────────────────────────────────────────────────

class TestRagNode:
    def test_no_top_pois_sets_no_pois_found_error(self):
        p = _make_pipeline()
        state = _base_state(origin="Austin, TX", destination="San Antonio, TX", top_pois=[])
        result = p._rag_node(state)
        assert result["error"] == "no_pois_found"

    def test_with_top_pois_sets_poi_context(self):
        p = _make_pipeline()
        state = _base_state(top_pois=[_fake_scored_poi()])
        result = p._rag_node(state)
        assert "poi_context" in result
        assert "Alamo" in result["poi_context"]
        assert "historic" in result["poi_context"]


# ── narrate node ───────────────────────────────────────────────────────────

class TestNarrateNode:
    def test_error_state_calls_fallback_chain(self):
        p = _make_pipeline()
        p._fallback_chain.generate.return_value = "Sorry, couldn't complete that route."
        state = _base_state(error="unparseable_query", fallback_reason="bad query")
        result = p._narrate_node(state)
        p._fallback_chain.generate.assert_called_once()
        assert result["narrative"] == "Sorry, couldn't complete that route."

    def test_success_state_calls_narrative_chain(self):
        p = _make_pipeline()
        p._narrative_chain.generate.return_value = "A lovely scenic drive..."
        state = _base_state(
            origin="Austin, TX",
            destination="San Antonio, TX",
            route_result=_fake_route_result(),
            top_pois=[_fake_scored_poi()],
        )
        result = p._narrate_node(state)
        p._narrative_chain.generate.assert_called_once()
        assert result["narrative"] == "A lovely scenic drive..."

    def test_narrative_key_in_result(self):
        p = _make_pipeline()
        p._fallback_chain.generate.return_value = "fallback text"
        result = p._narrate_node(_base_state(error="geocode_failed", fallback_reason="bad city"))
        assert "narrative" in result
