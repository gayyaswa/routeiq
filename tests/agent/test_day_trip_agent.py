"""Tests for the Day Trip Planner LangGraph agent."""
from __future__ import annotations
import uuid
import pytest
from typing import Optional
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from routeiq.agent.day_trip_agent import (
    build_day_trip_graph,
    DayTripItinerary,
    ItineraryStop,
    _schedule_stops,
    _minutes_to_timestr,
    _timestr_to_minutes,
)
from routeiq.graph.route_result import RouteResult
from langgraph.types import Command


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_stop(**kwargs) -> ItineraryStop:
    defaults = dict(
        order=1,
        name="Alcatraz Island",
        category="tourism",
        lat=37.8267,
        lon=-122.4233,
        arrival_time="9:00 AM",
        departure_time="11:00 AM",
        visit_duration_min=120,
        why_visit="Historic island prison in San Francisco Bay.",
        visitor_quote="TripAdvisor: 'Unmissable — the history is extraordinary.'",
        visitor_summary="Visitors consistently praise the audio tour and stunning bay views.",
        activities=["Take the audio tour", "Walk the cellblock"],
        rating=4.6,
        review_count=12000,
        review_source="TripAdvisor",
        photo_urls=["https://example.com/alcatraz.jpg"],
    )
    defaults.update(kwargs)
    return ItineraryStop(**defaults)


def _make_itinerary(**kwargs) -> DayTripItinerary:
    defaults = dict(
        city="San Francisco, CA",
        date="today",
        total_hours=8.0,
        stops=[_make_stop()],
        narrative=None,
    )
    defaults.update(kwargs)
    return DayTripItinerary(**defaults)


def _mock_llm(itinerary: Optional[DayTripItinerary] = None):
    """Return a mock LLM that exits the ReAct loop immediately and returns a structured itinerary."""
    if itinerary is None:
        itinerary = _make_itinerary()

    mock = MagicMock()
    # Phase 1: bind_tools → invoke returns AIMessage with no tool_calls (exits ReAct loop)
    mock.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[])
    # Phase 2: with_structured_output → invoke returns validated Pydantic itinerary
    mock.with_structured_output.return_value.invoke.return_value = itinerary
    # Narrate node: invoke returns plain AIMessage
    mock.invoke.return_value = AIMessage(content="What a beautiful day trip through San Francisco!")
    return mock


def _initial_state():
    return {
        "messages": [],
        "city": "San Francisco, CA",
        "preferences": ["history", "nature"],
        "time_budget_hours": 8.0,
        "start_time": "9:00 AM",
        "draft_itinerary": None,
        "route_coords": None,
        "approved": False,
        "narrative": None,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestInterruptFires:
    @pytest.fixture(autouse=True)
    def _no_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._schedule_stops",
            lambda stops, *_: (stops, []),
        )

    def test_graph_pauses_at_review_node(self):
        """Streaming the initial state must pause at the 'review' interrupt."""
        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=_mock_llm()):
            # Consume the stream to drive the graph to the interrupt point
            for _ in graph.stream(_initial_state(), config=config):
                pass

        snapshot = graph.get_state(config)
        assert "review" in snapshot.next, (
            f"Expected graph to pause at 'review', got next={snapshot.next}"
        )


class TestResumeApproved:
    @pytest.fixture(autouse=True)
    def _no_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._schedule_stops",
            lambda stops, *_: (stops, []),
        )

    def test_approved_reaches_narrate_and_sets_narrative(self):
        """Resuming with approved=True must run the narrate node and populate narrative."""
        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=_mock_llm()):
            # Drive to interrupt
            for _ in graph.stream(_initial_state(), config=config):
                pass

            # Resume approved
            final_state = graph.invoke(
                Command(resume={"approved": True}), config=config
            )

        assert final_state["narrative"] is not None
        assert len(final_state["narrative"]) > 0


class TestResumeRefine:
    @pytest.fixture(autouse=True)
    def _no_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._schedule_stops",
            lambda stops, *_: (stops, []),
        )

    def test_refine_loops_back_to_plan(self):
        """Resuming with approved=False must re-enter the plan node and produce a new draft."""
        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        second_itinerary = _make_itinerary(
            stops=[_make_stop(name="Golden Gate Park")]
        )
        mock = _mock_llm()
        # Second plan call returns a different itinerary
        mock.with_structured_output.return_value.invoke.side_effect = [
            _make_itinerary(),        # first plan pass
            second_itinerary,         # second plan pass after refine
        ]

        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock):
            # Drive to interrupt
            for _ in graph.stream(_initial_state(), config=config):
                pass

            # Resume with refine feedback → drives back to plan
            for _ in graph.stream(
                Command(resume={"approved": False, "feedback": "Add more nature stops"}),
                config=config,
            ):
                pass

        snapshot = graph.get_state(config)
        # Graph should be paused at review again with the new draft
        assert "review" in snapshot.next
        new_draft = snapshot.values.get("draft_itinerary") or {}
        stop_names = [s["name"] for s in new_draft.get("stops", [])]
        assert "Golden Gate Park" in stop_names


class TestScheduleStops:
    """Unit tests for _schedule_stops() — the deterministic post-processing step."""

    def _make_stops(self, n: int, visit_min: int = 60) -> list[dict]:
        """Create n fake stop dicts with lat/lon spread and no composite_score."""
        return [
            {
                "name": f"Stop {i}",
                "category": "tourism",
                "lat": 37.77 + i * 0.01,
                "lon": -122.41 + i * 0.01,
                "visit_duration_min": visit_min,
                "arrival_time": "TBD",
                "departure_time": "TBD",
            }
            for i in range(n)
        ]

    def _mock_geocode(self):
        """Mock return value for ox.geocode() — (lat, lon) tuple."""
        return (37.77, -122.41)

    def _fake_route_result(self, drive_time_min: float = 8.0) -> RouteResult:
        return RouteResult(
            route_nodes=[1, 2, 3],
            route_coords=[(37.77, -122.41), (37.78, -122.42)],
            length_km=4.0,
            drive_time_min=drive_time_min,
        )

    def test_empty_stops_returns_empty(self):
        stops, coords = _schedule_stops([], "9:00 AM", 8.0, "San Francisco, CA")
        assert stops == []
        assert coords == []

    def test_uses_stop_centroid_skips_geocode(self):
        """geocode is never called when stops have valid coordinates."""
        stops = self._make_stops(2)
        with patch("osmnx.geocode") as mock_geocode, \
             patch("routeiq.graph.graph_loader.GraphLoader") as mock_gl:
            mock_gl.return_value.load.side_effect = RuntimeError("no graph")
            result_stops, coords = _schedule_stops(stops, "9:00 AM", 8.0, "San Francisco, CA")
        mock_geocode.assert_not_called()
        assert result_stops == stops
        assert coords == []

    def test_returns_original_on_graph_load_failure(self):
        stops = self._make_stops(2)
        with patch("osmnx.geocode", return_value=self._mock_geocode()), \
             patch("routeiq.graph.graph_loader.GraphLoader") as mock_gl:
            mock_gl.return_value.load.side_effect = RuntimeError("cache miss")
            result_stops, coords = _schedule_stops(stops, "9:00 AM", 8.0, "San Francisco, CA")
        assert result_stops == stops
        assert coords == []

    def test_first_stop_gets_start_time(self):
        stops = self._make_stops(2, visit_min=60)
        fake_result = self._fake_route_result(drive_time_min=8.0)
        with patch("osmnx.geocode", return_value=self._mock_geocode()), \
             patch("routeiq.graph.graph_loader.GraphLoader") as mock_gl, \
             patch("routeiq.graph.route_graph.RouteGraph") as mock_rg:
            mock_gl.return_value.load.return_value = MagicMock()
            mock_rg.return_value.find_route.return_value = fake_result
            result_stops, _ = _schedule_stops(stops, "9:00 AM", 8.0, "San Francisco, CA")
        assert result_stops[0]["arrival_time"] == "9:00 AM"

    def test_first_stop_gets_11am_start_time(self):
        """Regression: 11:00 AM start should propagate to first stop, not silently fall back to 9 AM."""
        stops = self._make_stops(2, visit_min=60)
        fake_result = self._fake_route_result(drive_time_min=8.0)
        with patch("osmnx.geocode", return_value=self._mock_geocode()), \
             patch("routeiq.graph.graph_loader.GraphLoader") as mock_gl, \
             patch("routeiq.graph.route_graph.RouteGraph") as mock_rg:
            mock_gl.return_value.load.return_value = MagicMock()
            mock_rg.return_value.find_route.return_value = fake_result
            result_stops, _ = _schedule_stops(stops, "11:00 AM", 8.0, "San Francisco, CA")
        assert result_stops[0]["arrival_time"] == "11:00 AM", (
            f"Expected 11:00 AM but got {result_stops[0]['arrival_time']} — "
            f"start_time may have fallen back to 9 AM default"
        )

    def test_timestr_to_minutes_all_selectbox_options(self):
        """Every option in the Start time selectbox must parse to a non-zero minute value."""
        options = ["8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM"]
        expected = [8 * 60, 9 * 60, 10 * 60, 11 * 60]
        for opt, exp in zip(options, expected):
            result = _timestr_to_minutes(opt)
            assert result == exp, f"_timestr_to_minutes({opt!r}) returned {result}, expected {exp}"
            assert result, f"_timestr_to_minutes({opt!r}) is falsy — will fall back to 9 AM default"

    def test_budget_drops_last_stop(self):
        # 3 stops × 30min visit + 15min transit (8 drive + 7 overhead).
        # Stop 3 departs at 11:00 AM; budget=1.5h ends at 10:30 AM → stop 3 trimmed → 2 remain.
        stops = self._make_stops(3, visit_min=30)
        fake_result = self._fake_route_result(drive_time_min=8.0)  # +7 overhead = 15 total
        with patch("osmnx.geocode", return_value=self._mock_geocode()), \
             patch("routeiq.graph.graph_loader.GraphLoader") as mock_gl, \
             patch("routeiq.graph.route_graph.RouteGraph") as mock_rg:
            mock_gl.return_value.load.return_value = MagicMock()
            mock_rg.return_value.find_route.return_value = fake_result
            result_stops, _ = _schedule_stops(stops, "9:00 AM", 1.5, "San Francisco, CA")
        assert len(result_stops) == 2

    def test_minutes_to_timestr_9am(self):
        assert _minutes_to_timestr(9 * 60) == "9:00 AM"

    def test_minutes_to_timestr_noon(self):
        assert _minutes_to_timestr(12 * 60) == "12:00 PM"

    def test_minutes_to_timestr_230pm(self):
        assert _minutes_to_timestr(14 * 60 + 30) == "2:30 PM"

    def test_minutes_to_timestr_midnight(self):
        assert _minutes_to_timestr(0) == "12:00 AM"

    def test_timestr_to_minutes_roundtrip(self):
        for mins in [0, 9 * 60, 12 * 60, 14 * 60 + 30, 23 * 60 + 59]:
            s = _minutes_to_timestr(mins)
            assert _timestr_to_minutes(s) == mins

    def test_timestr_to_minutes_invalid(self):
        assert _timestr_to_minutes("not a time") is None


class TestIterZeroGuard:
    """Verify the iter==0 no-tool-call retry guard in _plan's ReAct loop."""

    @pytest.fixture(autouse=True)
    def _no_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._schedule_stops",
            lambda stops, *_: (stops, []),
        )

    def test_retries_once_when_first_call_has_no_tools(self):
        """If the LLM returns no tool calls on iter=0, the guard nudges once and retries."""
        mock = _mock_llm()
        # First call → no tool_calls (triggers guard); second call → no tool_calls (exits loop)
        no_tool_response = AIMessage(content="Here is my plan...", tool_calls=[])
        mock.bind_tools.return_value.invoke.side_effect = [no_tool_response, no_tool_response]

        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock):
            for _ in graph.stream(_initial_state(), config=config):
                pass

        # Guard must have triggered: LLM invoked twice before exiting the ReAct loop
        assert mock.bind_tools.return_value.invoke.call_count == 2

    def test_no_retry_when_first_call_has_tools(self):
        """If the LLM calls tools on iter=0, the guard does not fire and no extra call is made."""
        from langchain_core.messages import ToolMessage

        mock = _mock_llm()
        tool_response = AIMessage(
            content="",
            tool_calls=[{"name": "find_city_pois", "args": {"city": "San Francisco, CA"}, "id": "tc1"}],
        )
        no_tool_response = AIMessage(content="Done.", tool_calls=[])

        def _fake_invoke(messages):
            call_n = mock.bind_tools.return_value.invoke.call_count
            return tool_response if call_n == 0 else no_tool_response

        mock.bind_tools.return_value.invoke.side_effect = _fake_invoke

        with patch("routeiq.agent.day_trip_agent._execute_tool",
                   return_value=ToolMessage(content="[]", tool_call_id="tc1", name="find_city_pois")):
            graph = build_day_trip_graph()
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}

            with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock):
                for _ in graph.stream(_initial_state(), config=config):
                    pass

        # Tool was called once at iter=0, then once more at iter=1 (no tool calls → exit)
        assert mock.bind_tools.return_value.invoke.call_count == 2


class TestChicagoEndToEnd:
    """End-to-end smoke test: agent must complete successfully with Chicago as the city."""

    @pytest.fixture(autouse=True)
    def _no_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._schedule_stops",
            lambda stops, *_: (stops, []),
        )

    def test_chicago_plan_reaches_review(self):
        """Graph must pause at the review interrupt for a Chicago day trip (not error out)."""
        chicago_state = {
            "messages": [],
            "city": "Chicago, IL",
            "preferences": ["history", "architecture"],
            "time_budget_hours": 8.0,
            "start_time": "9:00 AM",
            "draft_itinerary": None,
            "route_coords": None,
            "approved": False,
            "narrative": None,
        }
        chicago_itinerary = DayTripItinerary(
            city="Chicago, IL",
            date="today",
            total_hours=8.0,
            stops=[
                ItineraryStop(
                    order=1,
                    name="Art Institute of Chicago",
                    category="museum",
                    lat=41.8796,
                    lon=-87.6237,
                    arrival_time="TBD",
                    departure_time="TBD",
                    visit_duration_min=120,
                    why_visit="World-class art museum in Grant Park.",
                )
            ],
        )
        mock = _mock_llm(chicago_itinerary)

        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock):
            for _ in graph.stream(chicago_state, config=config):
                pass

        snapshot = graph.get_state(config)
        assert "review" in snapshot.next
        draft = snapshot.values.get("draft_itinerary") or {}
        assert draft.get("city") == "Chicago, IL"
        assert len(draft.get("stops", [])) >= 1


class TestItinerarySchema:
    def test_valid_itinerary_validates_ok(self):
        """DayTripItinerary with all fields must validate without errors."""
        stop = _make_stop()
        itinerary = _make_itinerary(stops=[stop])
        assert itinerary.city == "San Francisco, CA"
        assert itinerary.stops[0].visitor_summary is not None
        assert itinerary.stops[0].photo_urls == ["https://example.com/alcatraz.jpg"]

    def test_optional_fields_default_to_none(self):
        """Optional fields on ItineraryStop must default to None / empty list."""
        stop = ItineraryStop(
            order=1, name="Test", category="tourism",
            lat=37.0, lon=-122.0,
            arrival_time="9:00 AM", departure_time="10:00 AM",
            visit_duration_min=60, why_visit="A historic site.",
        )
        assert stop.visitor_quote is None
        assert stop.visitor_summary is None
        assert stop.photo_urls == []
        assert stop.activities == []
