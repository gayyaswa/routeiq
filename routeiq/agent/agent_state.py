from __future__ import annotations
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class DayTripState(TypedDict):
    """Shared state for the Day Trip Planner LangGraph graph (Pipeline pattern)."""

    messages: Annotated[list[BaseMessage], add_messages]
    city: str
    preferences: list[str]
    time_budget_hours: float
    start_time: str                 # e.g. "9:00 AM"
    draft_itinerary: dict | None
    approved: bool
    narrative: str | None
