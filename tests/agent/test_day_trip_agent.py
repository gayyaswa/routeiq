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
)
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
        "approved": False,
        "narrative": None,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestInterruptFires:
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
