from typing import Annotated, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class DayTripState(TypedDict):
    """Shared state for the Day Trip Planner LangGraph graph (Pipeline pattern)."""

    messages: Annotated[List[BaseMessage], add_messages]
    city: str
    preferences: List[str]
    time_budget_hours: float
    start_time: str                 # e.g. "9:00 AM"
    draft_itinerary: Optional[dict]
    approved: bool
    narrative: Optional[str]
