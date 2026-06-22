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
    route_coords: Optional[List[tuple]]  # (lat, lon) pairs; None until _schedule_stops runs
    approved: bool
    narrative: Optional[str]
    activities: List[str]               # ["hiking", "kids"] — from UI or query parser
    user_context: str                   # "scenic coastal hiking" — adjective phrases
    activity_fallback_note: Optional[str]  # set when a requested activity has no POIs
