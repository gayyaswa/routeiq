"""Tests for activity-aware behaviour in the Day Trip Planner agent."""
from __future__ import annotations
import json
import uuid
import pytest
from typing import Optional
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, ToolMessage

from routeiq.agent.day_trip_agent import (
    build_day_trip_graph,
    DayTripItinerary,
    ItineraryStop,
)
from langgraph.types import Command


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stop(**kwargs) -> ItineraryStop:
    defaults = dict(
        order=1, name="Barton Springs", category="natural",
        lat=30.2641, lon=-97.7714,
        arrival_time="9:00 AM", departure_time="11:00 AM",
        visit_duration_min=120,
        why_visit="A spring-fed pool in Austin, Texas.",
    )
    defaults.update(kwargs)
    return ItineraryStop(**defaults)


def _make_itinerary(city="Austin, TX", stops=None) -> DayTripItinerary:
    return DayTripItinerary(
        city=city,
        date="today",
        total_hours=8.0,
        stops=stops or [_make_stop()],
    )


def _mock_llm(itinerary: Optional[DayTripItinerary] = None):
    mock = MagicMock()
    mock.bind_tools.return_value.invoke.return_value = AIMessage(content="", tool_calls=[])
    mock.with_structured_output.return_value.invoke.return_value = itinerary or _make_itinerary()
    mock.invoke.return_value = AIMessage(content="Great day trip through Austin!")
    return mock


def _state(activities=None, user_context=""):
    return {
        "messages": [],
        "city": "Austin, TX",
        "preferences": ["outdoor"],
        "time_budget_hours": 8.0,
        "start_time": "9:00 AM",
        "activities": activities or [],
        "user_context": user_context,
        "draft_itinerary": None,
        "route_coords": None,
        "approved": False,
        "narrative": None,
        "activity_fallback_note": None,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestActivityFallbackNote:
    """Verify that _plan computes activity_fallback_note when activities are unmatched."""

    @pytest.fixture(autouse=True)
    def _no_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._schedule_stops",
            lambda stops, *_: (stops, []),
        )
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._backfill_images",
            lambda stops: None,
        )

    def _run_with_select_tool(self, activities, select_content: str):
        """Drive the graph to the review interrupt with a mocked select_pois_for_day call."""
        mock = _mock_llm()
        tool_response = AIMessage(
            content="",
            tool_calls=[{
                "name": "select_pois_for_day",
                "args": {
                    "city": "Austin, TX",
                    "requested_activities": activities,
                    "user_context": "scenic",
                    "total_stops": 5,
                },
                "id": "tc1",
            }],
        )
        no_tool_response = AIMessage(content="Done.", tool_calls=[])
        mock.bind_tools.return_value.invoke.side_effect = [tool_response, no_tool_response]

        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        fake_tool_msg = ToolMessage(
            content=select_content,
            tool_call_id="tc1",
            name="select_pois_for_day",
        )
        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock), \
             patch("routeiq.agent.day_trip_agent._execute_tool", return_value=fake_tool_msg):
            for _ in graph.stream(_state(activities=activities, user_context="scenic"), config=config):
                pass

        return graph.get_state(config).values

    def test_fallback_note_set_when_activity_unmatched(self):
        activities = ["hiking", "kayaking"]
        # Only hiking is matched; kayaking has no POIs
        content = json.dumps([{"name": "Trail Peak", "matched_activities": ["hiking"]}])
        state_values = self._run_with_select_tool(activities, content)
        note = state_values.get("activity_fallback_note")
        assert note is not None
        assert "kayaking" in note

    def test_fallback_note_none_when_all_activities_matched(self):
        activities = ["hiking"]
        content = json.dumps([{"name": "Trail Peak", "matched_activities": ["hiking"]}])
        state_values = self._run_with_select_tool(activities, content)
        assert state_values.get("activity_fallback_note") is None

    def test_fallback_note_mentions_city(self):
        activities = ["kayaking"]
        content = json.dumps([])  # no matches at all
        state_values = self._run_with_select_tool(activities, content)
        note = state_values.get("activity_fallback_note")
        assert note is not None
        assert "Austin" in note

    def test_no_fallback_note_when_no_activities(self):
        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        mock = _mock_llm()
        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock):
            for _ in graph.stream(_state(activities=[]), config=config):
                pass
        snapshot = graph.get_state(config)
        assert snapshot.values.get("activity_fallback_note") is None


class TestActivitiesInState:
    """Verify the graph accepts and threads through the new state fields."""

    @pytest.fixture(autouse=True)
    def _no_schedule(self, monkeypatch):
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._schedule_stops",
            lambda stops, *_: (stops, []),
        )
        monkeypatch.setattr(
            "routeiq.agent.day_trip_agent._backfill_images",
            lambda stops: None,
        )

    def test_graph_pauses_at_review_with_activities(self):
        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        mock = _mock_llm()
        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock):
            for _ in graph.stream(_state(activities=["hiking", "kids"]), config=config):
                pass
        snapshot = graph.get_state(config)
        assert "review" in snapshot.next

    def test_approved_with_activities_produces_narrative(self):
        graph = build_day_trip_graph()
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        mock = _mock_llm()
        with patch("routeiq.agent.day_trip_agent.create_llm", return_value=mock):
            for _ in graph.stream(_state(activities=["hiking"]), config=config):
                pass
            final = graph.invoke(Command(resume={"approved": True}), config=config)
        assert final.get("narrative") is not None
