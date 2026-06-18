from __future__ import annotations
import logging
import threading
import time
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from routeiq.agent.agent_state import DayTripState
from routeiq.agent.tools import ALL_TOOLS
from routeiq.insights.prompts.day_trip_planner import DAY_TRIP_PLANNER_PROMPT
from routeiq.llm_factory import create_llm

# ── Per-run progress registry (thread-safe) ───────────────────────────────────
# Maps LangGraph thread_id → shared dict that app.py polls every 0.5s.
# Structure mirrors Route Planner: {"current": str, "done": set, "subtask": str}

_progress_lock = threading.Lock()
_progress_registry: dict[str, dict] = {}

# Maps agent tool names → logical stepper step keys
_TOOL_TO_STEP: dict[str, str] = {
    "find_city_pois": "find_pois",
    "enrich_poi_details": "find_pois",
    "get_travel_time": "find_pois",
    "estimate_visit_duration": "find_pois",
    "search_poi_by_name": "find_pois",
    "rate_pois": "rate_pois",
}


def register_progress(thread_id: str, d: dict) -> None:
    """Register a shared progress dict for a planning run. Called by app.py before thread start."""
    with _progress_lock:
        _progress_registry[thread_id] = d


def unregister_progress(thread_id: str) -> None:
    """Remove the progress dict after planning completes."""
    with _progress_lock:
        _progress_registry.pop(thread_id, None)


def _emit_progress(thread_id: str, step: str, subtask: str = "") -> None:
    """Advance progress state: marks previous step done, sets new current step."""
    with _progress_lock:
        d = _progress_registry.get(thread_id)
    if d is None:
        return
    current = d.get("current")
    if current and current != step:
        done: set = set(d.get("done") or set())
        done.add(current)
        d["done"] = done
    d["current"] = step
    d["subtask"] = subtask

# ── Output schemas ────────────────────────────────────────────────────────────

class ItineraryStop(BaseModel):
    """One stop in the day trip itinerary."""
    order: int
    name: str
    category: str
    lat: float
    lon: float
    arrival_time: str
    departure_time: str
    visit_duration_min: int
    why_visit: str = Field(description="One factual sentence from Wikipedia only.")
    visitor_quote: Optional[str] = Field(
        None, description="Single most vivid snippet prefixed with review_source name."
    )
    visitor_summary: Optional[str] = Field(
        None, description="1-2 sentence synthesis of overall visitor sentiment from all snippets."
    )
    activities: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    review_source: Optional[str] = None
    photo_urls: List[str] = Field(
        default_factory=list,
        description="Copy photo_urls exactly from rate_pois tool results. Do not invent URLs.",
    )
    image_url: Optional[str] = None
    hours: Optional[str] = None


class DayTripItinerary(BaseModel):
    """Full day trip itinerary produced by the agent."""
    city: str
    date: str
    total_hours: float
    stops: List[ItineraryStop]
    narrative: Optional[str] = None




def _execute_tool(tool_call: dict[str, Any]) -> ToolMessage:
    """Dispatch a single tool call and return the ToolMessage result."""
    name = tool_call["name"]
    args = tool_call["args"]
    tool_map = {t.name: t for t in ALL_TOOLS}
    if name not in tool_map:
        result = f"Unknown tool: {name}"
    else:
        try:
            result = tool_map[name].invoke(args)
        except Exception as exc:
            result = f"Tool error: {exc}"
    return ToolMessage(content=str(result), tool_call_id=tool_call["id"], name=name)


# ── Schedule helpers ─────────────────────────────────────────────────────────

_TRANSITION_OVERHEAD_MIN = 7.0  # parking + walk to entrance, separate from visit_duration_min


def _minutes_to_timestr(total: float) -> str:
    """Convert minutes-since-midnight to '9:00 AM' / '2:30 PM'."""
    h = int(total // 60) % 24
    m = int(total % 60)
    period = "AM" if h < 12 else "PM"
    display_h = h % 12 or 12
    return f"{display_h}:{m:02d} {period}"


def _timestr_to_minutes(s: str) -> Optional[float]:
    """Parse '9:00 AM' or '2:30 PM' → minutes since midnight. Returns None on failure."""
    import re as _re
    match = _re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM)", s.strip(), _re.IGNORECASE)
    if not match:
        return None
    h, mins, period = int(match.group(1)), int(match.group(2)), match.group(3).upper()
    if period == "PM" and h != 12:
        h += 12
    elif period == "AM" and h == 12:
        h = 0
    return float(h * 60 + mins)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (no external deps)."""
    import math
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _schedule_stops(
    stops: List[dict],
    start_time: str,
    time_budget_hours: float,
    city: str,
) -> tuple:
    """
    Replace LLM-hallucinated times with real A* road times and trim stops to budget.
    Returns (updated_stops, route_coords). Falls back to (original_stops, []) on any error.
    """
    if not stops:
        return stops, []

    try:
        import osmnx as ox  # lazy — project convention
        from routeiq.graph.graph_loader import GraphLoader
        from routeiq.graph.route_graph import RouteGraph

        start_min = _timestr_to_minutes(start_time) or 9 * 60.0
        budget_min = time_budget_hours * 60.0

        # Prefer stop centroid — coords come from OSM/Overpass via find_city_pois,
        # not from the LLM, so they're always accurate regardless of KG state.
        # Fall back to geocoding only when stops list is empty (shouldn't happen).
        # Avoid bare ox.geocode(city): "Berkeley, CA" → British Columbia via Nominatim
        # because "CA" is the ISO country code for Canada.
        if stops:
            lat = sum(s["lat"] for s in stops) / len(stops)
            lon = sum(s["lon"] for s in stops) / len(stops)
        else:
            lat, lon = ox.geocode(city + ", USA")
        logger.debug("schedule city=%r centroid=(%.4f,%.4f) bbox=N%.3f/S%.3f/E%.3f/W%.3f",
                     city, lat, lon, lat+0.15, lat-0.15, lon+0.15, lon-0.15)

        G = GraphLoader().load(
            north=lat + 0.15, south=lat - 0.15,
            east=lon + 0.15,  west=lon - 0.15,
        )
        rg = RouteGraph(G)
        logger.debug("schedule graph loaded — %d nodes", G.number_of_nodes())

        for s in stops:
            logger.debug("schedule input stop: %r lat=%.4f lon=%.4f", s.get("name"), s.get("lat", 0), s.get("lon", 0))

        # Nearest-neighbor sort: best composite_score first, then greedy by distance
        remaining = list(stops)
        if any("composite_score" in s for s in remaining):
            first = max(remaining, key=lambda s: s.get("composite_score") or 0.0)
            remaining.remove(first)
            sorted_stops: List[dict] = [first]
            while remaining:
                last = sorted_stops[-1]
                nearest = min(
                    remaining,
                    key=lambda s: _haversine_km(last["lat"], last["lon"], s["lat"], s["lon"]),
                )
                remaining.remove(nearest)
                sorted_stops.append(nearest)
        else:
            sorted_stops = list(stops)

        # Build timeline; leg_coord_slices[0] is empty (no drive before first stop)
        leg_coord_slices: List[list] = [[]]
        current_min = start_min

        for i, stop in enumerate(sorted_stops):
            stop = dict(stop)
            stop["arrival_time"] = _minutes_to_timestr(current_min)
            visit_dur = float(stop.get("visit_duration_min") or 60.0)
            stop["departure_time"] = _minutes_to_timestr(current_min + visit_dur)
            current_min += visit_dur
            sorted_stops[i] = stop

            if i + 1 < len(sorted_stops):
                nxt = sorted_stops[i + 1]
                try:
                    result = rg.find_route(stop["lat"], stop["lon"], nxt["lat"], nxt["lon"])
                    drive_min = result.drive_time_min + _TRANSITION_OVERHEAD_MIN
                    first_c = result.route_coords[0] if result.route_coords else None
                    last_c  = result.route_coords[-1] if result.route_coords else None
                    logger.debug("schedule leg %d→%d %r→%r: OK %d coords first=%s last=%s",
                                 i, i+1, stop.get("name"), nxt.get("name"),
                                 len(result.route_coords), first_c, last_c)
                    leg_coord_slices.append(result.route_coords)
                except Exception as exc:
                    logger.debug("schedule leg %d→%d %r→%r: FAILED %s",
                                 i, i+1, stop.get("name"), nxt.get("name"), exc)
                    leg_coord_slices.append([])
                    drive_min = 15.0
                current_min += drive_min

        # Trim tail while last stop's departure exceeds budget
        end_min = start_min + budget_min
        while len(sorted_stops) > 1:
            last_dep = _timestr_to_minutes(sorted_stops[-1]["departure_time"])
            if last_dep is None or last_dep <= end_min:
                break
            sorted_stops.pop()
            if len(leg_coord_slices) > len(sorted_stops):
                leg_coord_slices.pop()

        all_coords: list = [
            c for slice_ in leg_coord_slices[: len(sorted_stops)] for c in slice_
        ]
        return sorted_stops, all_coords

    except Exception as exc:
        logger.warning("_schedule_stops fallback — returning original stops unscheduled: %s", exc)
        return stops, []


# ── Image backfill ────────────────────────────────────────────────────────────

def _backfill_images(stops: list[dict]) -> None:
    """Fill image_url from Wikipedia for any stop that has no provider photo_urls.

    Skips stops that already have at least one photo from TripAdvisor/Foursquare.
    Runs fetches in parallel — Wikipedia lookup is ~0.3 s each.
    """
    from concurrent.futures import ThreadPoolExecutor
    from routeiq.graph.poi import POI
    from routeiq.rag.wikipedia_fetcher import WikipediaFetcher

    needs_image = [
        s for s in stops
        if not (s.get("photo_urls") or s.get("image_url"))
    ]
    if not needs_image:
        return

    def _fetch_one(stop: dict) -> None:
        poi = POI(
            name=stop["name"],
            category=stop.get("category", "tourism"),
            lat=stop.get("lat", 0.0),
            lon=stop.get("lon", 0.0),
            osm_id="agent_img_backfill",
        )
        try:
            WikipediaFetcher().enrich(poi)
            if poi.image_url:
                stop["image_url"] = poi.image_url
        except Exception:
            pass  # best-effort; missing image is non-fatal

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_fetch_one, needs_image))


# ── Graph nodes ───────────────────────────────────────────────────────────────

def _plan(state: DayTripState, config: Optional[RunnableConfig] = None) -> dict:
    """ReAct tool loop, then a structured-output call to extract the validated itinerary."""
    t0 = time.perf_counter()
    thread_id: str = ((config or {}).get("configurable") or {}).get("thread_id", "")
    print(f"[dt_agent] _plan start city={state['city']}", flush=True)
    llm = create_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # First pass: build messages from prompt template.
    # Re-plan pass: messages already contain conversation history + feedback HumanMessage.
    if not state["messages"]:
        messages = DAY_TRIP_PLANNER_PROMPT.format_messages(
            city=state["city"],
            preferences=", ".join(state["preferences"]) or "any",
            hours=state["time_budget_hours"],
            start_time=state["start_time"],
        )
    else:
        messages = list(state["messages"])

    # Phase 1 — ReAct loop: execute tools until the LLM stops calling them
    max_iterations = 12
    for iteration in range(max_iterations):
        response: AIMessage = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            print(f"[dt_agent] ReAct loop: iter={iteration} no tool calls → stopping", flush=True)
            break

        tool_names = [tc["name"] for tc in response.tool_calls]
        print(f"[dt_agent] ReAct loop: iter={iteration} tools={tool_names}", flush=True)

        # Emit progress for the first tool in each iteration
        if thread_id and tool_names:
            step = _TOOL_TO_STEP.get(tool_names[0], "find_pois")
            label = tool_names[0].replace("_", " ")
            _emit_progress(thread_id, step, label)

        for tc in response.tool_calls:
            messages.append(_execute_tool(tc))

    # Phase 2 — Structured extraction: the full conversation becomes context for a
    # validated Pydantic parse. This guarantees all fields are present and typed correctly.
    if thread_id:
        _emit_progress(thread_id, "extract", "Structuring itinerary…")

    structured_llm = llm.with_structured_output(DayTripItinerary)
    extraction_prompt = (
        "Based on all the tool results above, produce the final day trip itinerary "
        "for " + state["city"] + ". Follow all faithfulness rules: visitor_quote from "
        "review snippets, visitor_summary synthesizing visitor sentiment, why_visit from "
        "Wikipedia only, activities grounded in Wikipedia and reviews. "
        "CRITICAL: copy lat, lon, photo_urls, rating, review_count, review_source, and hours "
        "EXACTLY from find_city_pois / rate_pois tool output — do not invent or modify these values."
    )
    itinerary: DayTripItinerary = structured_llm.invoke(
        messages + [HumanMessage(content=extraction_prompt)]
    )
    itinerary_dict = itinerary.model_dump()

    if thread_id:
        _emit_progress(thread_id, "extract", "Computing real route…")

    scheduled_stops, route_coords = _schedule_stops(
        itinerary_dict.get("stops") or [],
        state["start_time"],
        state["time_budget_hours"],
        state["city"],
    )

    # Backfill Wikipedia thumbnails for stops that got no TripAdvisor/Foursquare photos.
    # Runs in parallel — each Wikipedia fetch is ~0.3 s, 8 stops ≈ 0.5 s total.
    if thread_id:
        _emit_progress(thread_id, "extract", "Fetching images…")
    _backfill_images(scheduled_stops)

    itinerary_dict["stops"] = scheduled_stops

    print(f"[dt_agent] _plan done in {time.perf_counter()-t0:.1f}s — {len(scheduled_stops)} stops", flush=True)
    return {"messages": messages, "draft_itinerary": itinerary_dict, "route_coords": route_coords}


def _review(state: DayTripState) -> Command:
    """Human-in-the-loop interrupt: surface draft to user and wait for approval."""
    decision: dict = interrupt(state["draft_itinerary"])

    if decision.get("approved"):
        return Command(goto="narrate", update={"approved": True})

    feedback = decision.get("feedback", "Please refine the itinerary.")
    return Command(
        goto="plan",
        update={
            "approved": False,
            "messages": [HumanMessage(content=f"Refine itinerary: {feedback}")],
        },
    )


def _narrate(state: DayTripState) -> dict:
    """Generate a warm 3–4 sentence narrative introduction for the day trip."""
    llm = create_llm()
    stop_names = [s["name"] for s in (state["draft_itinerary"] or {}).get("stops", [])][:3]
    prompt = (
        f"Write a warm, engaging 3–4 sentence narrative introducing this day trip to "
        f"{state['city']}. Mention these stops: {', '.join(stop_names)}. "
        "Do not use bullet points or markdown headers."
    )
    response = llm.invoke(list(state["messages"]) + [HumanMessage(content=prompt)])
    return {"narrative": response.content}


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_day_trip_graph() -> Any:
    """Build and compile the Day Trip Planner LangGraph state machine (Pipeline pattern)."""
    builder = StateGraph(DayTripState)

    builder.add_node("plan", _plan)
    builder.add_node("review", _review)
    builder.add_node("narrate", _narrate)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "review")
    builder.add_edge("narrate", "__end__")

    checkpointer = MemorySaver()
    # interrupt() inside _review is the canonical LangGraph 0.6.x pattern.
    # interrupt_before=["review"] was removed because in 0.6.x it fires before
    # the _plan checkpoint is committed, so get_state() sees draft_itinerary=None.
    return builder.compile(checkpointer=checkpointer)
