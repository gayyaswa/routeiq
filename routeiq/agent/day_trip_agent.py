from __future__ import annotations
import json
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
    "select_pois_for_day": "find_pois",
    "enrich_poi_details": "find_pois",
    "get_travel_time": "find_pois",
    "estimate_visit_duration": "find_pois",
    "search_poi_by_name": "find_pois",
    "rate_pois": "rate_pois",
    "query_poi_context": "rag",
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
    now = time.perf_counter()
    current = d.get("current")
    if current and current != step:
        # Accumulate elapsed wall-clock for the step that just finished.
        # += so multi-iteration ReAct loops (rate_pois called twice, etc.) sum correctly.
        step_start = d.get("step_start")
        if step_start is not None:
            step_times: dict = d.get("step_times") or {}
            step_times[current] = step_times.get(current, 0.0) + (now - step_start)
            d["step_times"] = step_times
        done: set = set(d.get("done") or set())
        done.add(current)
        d["done"] = done
    if step != current:
        d["step_start"] = now
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
    description_source: Optional[str] = Field(
        None, description="Copy exactly from rate_pois: 'wikipedia', 'ai_generated', or ''."
    )
    activity_source: Optional[str] = Field(
        None, description="Copy exactly from rate_pois: 'osm', 'ai_generated', or ''."
    )
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




def _execute_tool(tool_call: dict[str, Any], poi_cache: dict) -> ToolMessage:
    """Dispatch a single tool call and return the ToolMessage result.

    poi_cache is injected into rate_pois via RunnableConfig so it can read and
    populate the in-session Layer 1 cache without the LLM knowing about it.
    """
    from routeiq.timing import log as _tlog
    name = tool_call["name"]
    args = tool_call["args"]
    tool_map = {t.name: t for t in ALL_TOOLS}
    if name not in tool_map:
        result = f"Unknown tool: {name}"
    else:
        try:
            _t0 = time.perf_counter()
            config = {"configurable": {"poi_cache": poi_cache}}
            result = tool_map[name].invoke(args, config=config)
            _tlog(f"tool={name} elapsed={time.perf_counter()-_t0:.2f}s")
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

        parsed_min = _timestr_to_minutes(start_time)
        logger.info("_schedule_stops: start_time=%r parsed_min=%s", start_time, parsed_min)
        start_min = parsed_min or 9 * 60.0
        if parsed_min is None:
            logger.warning("_schedule_stops: could not parse start_time=%r, falling back to 9:00 AM", start_time)
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

        # Geographic nearest-neighbor route: anchor on the northernmost stop so the
        # day trip flows as a traversal (not score-first, which puts islands/extremes first).
        remaining = list(stops)
        first = max(remaining, key=lambda s: s.get("lat") or 0.0)
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


# ── Anthropic extraction helper ───────────────────────────────────────────────

def _extract_itinerary_anthropic(llm, messages: list) -> "DayTripItinerary":
    """Extract a DayTripItinerary via raw llm.invoke() + manual JSON parse.

    with_structured_output tool-calling causes Claude to omit the stops array
    (treats it as an optional arg). Embedding the schema in a system message and
    parsing the raw text response is reliable regardless of response size.
    """
    import json as _json
    import re as _re
    from langchain_core.messages import SystemMessage

    schema = DayTripItinerary.model_json_schema()
    system_content = (
        "Output ONLY a valid JSON object — no explanation, no markdown code fences, "
        "no preamble. The JSON must exactly match this schema:\n\n"
        f"{_json.dumps(schema, indent=2)}\n\n"
        "The 'stops' array is REQUIRED. Include every stop from the tool results."
    )
    # Default max_tokens for ChatAnthropic is 1024 — too small for 8-10 stops of JSON.
    response = llm.bind(max_tokens=8192).invoke([SystemMessage(content=system_content)] + list(messages))
    text = (response.content or "").strip()
    # Strip markdown fences if Claude wraps its output
    if "```" in text:
        text = _re.sub(r"```(?:json)?\n?", "", text).strip().rstrip("`").strip()
    data = _json.loads(text)
    return DayTripItinerary(**data)


# ── Graph nodes ───────────────────────────────────────────────────────────────

def _plan(state: DayTripState, config: Optional[RunnableConfig] = None) -> dict:
    """ReAct tool loop, then a structured-output call to extract the validated itinerary."""
    t0 = time.perf_counter()
    thread_id: str = ((config or {}).get("configurable") or {}).get("thread_id", "")
    logger.info("_plan start city=%s start_time=%r messages_in_state=%d",
                state["city"], state.get("start_time"), len(state["messages"]))
    llm = create_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    # Carry forward the in-session POI cache so rate_pois skips already-processed POIs.
    poi_cache: dict = dict(state.get("poi_cache") or {})

    # First pass: build messages from prompt template.
    # Re-plan pass: messages already contain conversation history + feedback HumanMessage.
    activities = state.get("activities") or []
    user_context = state.get("user_context") or ""

    if not state["messages"]:
        messages = DAY_TRIP_PLANNER_PROMPT.format_messages(
            city=state["city"],
            preferences=", ".join(state["preferences"]) or "any",
            hours=state["time_budget_hours"],
            start_time=state["start_time"],
            activities=", ".join(activities) if activities else "none",
            user_context=user_context or "none",
        )
    else:
        messages = list(state["messages"])
        # Strengthen the last refinement message so the LLM re-calls tools instead of
        # treating existing tool results as sufficient.
        last = messages[-1]
        if isinstance(last, HumanMessage) and last.content.startswith("Refine itinerary:"):
            messages[-1] = HumanMessage(content=(
                f"{last.content}\n\n"
                f"Call find_city_pois and rate_pois again to discover POIs that match the "
                f"updated preferences above, then rebuild the itinerary from the new results."
            ))

    logger.info("_plan phase=fresh_run=%s prompt_messages=%d",
                not bool(state["messages"]), len(messages))

    # Phase 1 — ReAct loop: execute tools until the LLM stops calling them
    from routeiq.timing import log as _tlog, clear as _tclear
    _tclear()
    max_iterations = 6
    _rate_pois_calls = 0       # guard: stop if rate_pois retried after already ran once
    _find_city_pois_calls = 0  # guard: stop if find_city_pois called again after results exist
    _iter_t0 = time.perf_counter()
    for iteration in range(max_iterations):
        _llm_t0 = time.perf_counter()
        response: AIMessage = llm_with_tools.invoke(messages)
        _llm_elapsed = time.perf_counter() - _llm_t0
        messages.append(response)

        if not response.tool_calls:
            if iteration == 0:
                # LLM skipped tools entirely on the very first call — this produces
                # empty tool results and a useless itinerary.  Nudge once and retry.
                logger.warning(
                    "ReAct loop iter=0 no tool calls (response_len=%d) — nudging LLM to call tools",
                    len(response.content or ""),
                )
                messages.pop()  # discard the tool-free response
                if activities:
                    nudge = (
                        f"You must call select_pois_for_day with "
                        f"requested_activities={activities!r} to discover activity-matched POIs "
                        f"for this city. Do not call find_city_pois — select_pois_for_day handles "
                        f"both activity matching and scenic fills. "
                        f"Please call the tools now — do not describe the plan, just call the tools."
                    )
                else:
                    nudge = (
                        "You must call find_city_pois first to discover POIs for this city. "
                        "Please call the tools now — do not describe the plan, just call the tools."
                    )
                messages.append(HumanMessage(content=nudge))
                continue
            _tlog(f"iter={iteration} llm_think={_llm_elapsed:.2f}s tools=[] → STOP total_react={time.perf_counter()-_iter_t0:.2f}s")
            logger.info("ReAct loop iter=%d no tool calls → stopping (response_len=%d)",
                        iteration, len(response.content or ""))
            break

        tool_names = [tc["name"] for tc in response.tool_calls]
        _tlog(f"iter={iteration} llm_think={_llm_elapsed:.2f}s tools={tool_names}")
        logger.debug("ReAct loop iter=%d tools=%s", iteration, tool_names)

        # Guard: stop if the LLM keeps calling rate_pois after it already ran once.
        # Happens when select_pois_for_day returns scenic fills (no activity match) and
        # the LLM retries hoping for different results — causes max_iterations exhaust.
        if "rate_pois" in tool_names and _rate_pois_calls >= 1:
            logger.warning(
                "ReAct loop iter=%d rate_pois called again (total=%d) — injecting stop nudge",
                iteration, _rate_pois_calls + 1,
            )
            messages.pop()  # discard the duplicate tool-call response
            messages.append(HumanMessage(content=(
                "rate_pois has already run. You have the rated POIs in the previous tool result. "
                "Do NOT call rate_pois, find_city_pois, or select_pois_for_day again. "
                "Stop calling tools — the itinerary builder will handle the rest."
            )))
            break

        if "rate_pois" in tool_names:
            _rate_pois_calls += 1

        # Guard: stop if the LLM calls find_city_pois or select_pois_for_day a second time.
        # Happens with unrecognised user contexts (e.g. "nightlife partying") — the LLM
        # retries POI discovery hoping for different results, burning iterations.
        _poi_discovery_tools = {"find_city_pois", "select_pois_for_day"}
        if _poi_discovery_tools & set(tool_names) and _find_city_pois_calls >= 1:
            logger.warning(
                "ReAct loop iter=%d POI discovery called again (total=%d, tools=%s) — injecting stop nudge",
                iteration, _find_city_pois_calls + 1, tool_names,
            )
            messages.pop()  # discard the duplicate tool-call response
            messages.append(HumanMessage(content=(
                "POI discovery has already run. The city POIs are in the previous tool results. "
                "Do NOT call find_city_pois or select_pois_for_day again. "
                "Call rate_pois on the existing POI list, then stop."
            )))
            continue  # let rate_pois run if it hasn't yet (don't break)

        if _poi_discovery_tools & set(tool_names):
            _find_city_pois_calls += 1

        # Emit progress for the first tool in each iteration
        if thread_id and tool_names:
            step = _TOOL_TO_STEP.get(tool_names[0], "find_pois")
            label = tool_names[0].replace("_", " ")
            _emit_progress(thread_id, step, label)

        for tc in response.tool_calls:
            messages.append(_execute_tool(tc, poi_cache))

    # Compute activity fallback note: which requested activities had no matching POIs?
    activity_fallback_note: str = ""
    if activities:
        covered: set[str] = set()
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.name == "select_pois_for_day":
                try:
                    stops_data = json.loads(msg.content)
                    if isinstance(stops_data, dict):
                        stops_data = stops_data.get("pois", [])
                    for s in (stops_data if isinstance(stops_data, list) else []):
                        covered.update(s.get("matched_activities") or [])
                except Exception:
                    pass
        uncovered = set(activities) - covered
        if uncovered:
            activity_fallback_note = (
                f"Heads up: we couldn't find {', '.join(sorted(uncovered))} spots in {state['city']}. "
                f"We've used the best scenic alternatives for those slots."
            )
            logger.info("_plan activity_fallback: uncovered=%s", uncovered)

    # Phase 2 — Structured extraction: build a FRESH prompt from tool results only.
    # Sending the full conversation (with the "Output JSON only" system instruction)
    # conflicts with with_structured_output's tool-calling mode on Nebius, causing
    # the model to return a raw JSON stub without the stops array.
    if thread_id:
        _emit_progress(thread_id, "extract", "Structuring itinerary…")

    def _extract_tool_content(msg: ToolMessage) -> str:
        """Unwrap {_note, pois} envelope from select_pois_for_day before extraction.
        The _note is a ReAct-loop hint only — it misleads the extraction LLM."""
        content = msg.content
        if msg.name == "select_pois_for_day":
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "pois" in parsed:
                    content = json.dumps(parsed["pois"])
            except Exception:
                pass
        return content

    tool_context = "\n\n---\n\n".join(
        _extract_tool_content(msg) for msg in messages if isinstance(msg, ToolMessage)
    ) or "No tool results available."

    # Parse rate_pois output to pin the top-5 must-include POIs.
    # Without this, the LLM freely picks stops and drops high-score landmarks like GGB.
    _must_include: list[str] = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "rate_pois":
            try:
                _rated = json.loads(msg.content)
                if isinstance(_rated, list):
                    _must_include = [
                        p["name"] for p in _rated[:5] if isinstance(p, dict) and p.get("name")
                    ]
            except Exception:
                pass
            break  # use only the first rate_pois call

    # Carry refinement feedback into the extraction prompt so the LLM applies it.
    # Start-time changes are not supported via refine — they require a fresh plan —
    # so strip them from the feedback to avoid contradicting state["start_time"].
    import re as _re
    refinement_feedback = next(
        (m.content.split("Refine itinerary:", 1)[-1].split("\n\n")[0].strip()
         for m in reversed(messages)
         if isinstance(m, HumanMessage) and "Refine itinerary:" in m.content),
        None,
    )
    if refinement_feedback and _re.search(r"\b(start|begin|starting)\b.{0,20}\b(at|from)\b.{0,10}\b\d{1,2}(:\d{2})?\s*(am|pm)\b", refinement_feedback, _re.IGNORECASE):
        logger.warning("_plan: refinement_feedback contains a start-time change (%r) — "
                       "ignoring it; start_time changes require a fresh plan run.", refinement_feedback)
        refinement_feedback = None
    refinement_note = (
        f"\nUser refinement request: \"{refinement_feedback}\"\n"
        f"IMPORTANT: Apply this refinement — include stops matching the updated preferences "
        f"and exclude any stop types the user wants removed.\n"
    ) if refinement_feedback else ""

    # Directive phrasing for extraction — "couldn't find X" causes Claude to omit stops.
    # Tell the model what to DO with the available POIs instead of what was missing.
    fallback_note_str = (
        f"\nNote: The requested activity was not available in {state['city']}. "
        f"The rate_pois tool results contain the top-rated scenic POIs — "
        f"use them to build all 8-10 stops.\n"
        if activity_fallback_note else ""
    )
    _must_include_note = (
        f"- MANDATORY: These top-rated POIs MUST appear in the stops list: "
        f"{', '.join(_must_include)}. "
        f"They are the highest-scoring results from rate_pois — never omit them.\n"
    ) if _must_include else ""

    extraction_messages = [
        HumanMessage(content=(
            f"Extract a structured day trip itinerary from these tool results.\n\n"
            f"Trip: {state['time_budget_hours']}-hour day in {state['city']} "
            f"starting at {state['start_time']}. "
            f"Preferences: {', '.join(state['preferences']) or 'any'}."
            f"{refinement_note}"
            f"{fallback_note_str}\n\n"
            f"=== TOOL RESULTS ===\n{tool_context}\n=== END TOOL RESULTS ===\n\n"
            f"Rules:\n"
            f"{_must_include_note}"
            f"- REQUIRED: The 'stops' array must always be present with at least 5 items. "
            f"If the user's context doesn't match the available POIs, include the 5-10 "
            f"highest-rated POIs from the tool results anyway — never omit the stops key.\n"
            f"- Include 8-10 stops matching the preferences.\n"
            f"- visitor_quote: the single most vivid snippet from all_snippets verbatim, "
            f"prefixed with the review_source name (e.g. 'TripAdvisor: ...'). "
            f"Set to null if all_snippets is empty or missing — do NOT fabricate quotes.\n"
            f"- visitor_summary: 1-2 sentences synthesising overall visitor sentiment from all_snippets. "
            f"Set to null if all_snippets is empty or missing — do NOT fabricate sentiment.\n"
            f"- why_visit: one factual sentence from the Wikipedia description only.\n"
            f"- activities: derived from Wikipedia and review snippets only.\n"
            f"- Copy lat, lon, photo_urls, rating, review_count, review_source, and hours "
            f"EXACTLY from the tool output — do not invent or modify these values.\n"
            f"- Set arrival_time and departure_time to 'TBD' (scheduling is done automatically).\n"
            f"- Use 'today' as the date value."
        ))
    ]

    import os as _os
    itinerary: DayTripItinerary | None = None
    for _attempt in range(2):
        try:
            if _os.environ.get("LLM_PROVIDER", "anthropic").lower() == "anthropic":
                itinerary = _extract_itinerary_anthropic(llm, extraction_messages)
            else:
                structured_llm = llm.with_structured_output(DayTripItinerary)
                itinerary = structured_llm.invoke(extraction_messages)
            break
        except Exception as _exc:
            logger.warning("Structured extraction attempt %d failed: %s", _attempt + 1, _exc)
            if _attempt == 1:
                raise
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

    logger.debug("_plan done in %.1fs — %d stops", time.perf_counter() - t0, len(scheduled_stops))
    return {
        "messages": messages,
        "draft_itinerary": itinerary_dict,
        "route_coords": route_coords,
        "activity_fallback_note": activity_fallback_note or None,
        "poi_cache": poi_cache,
    }


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
    stops = (state["draft_itinerary"] or {}).get("stops", [])
    stop_names = [s["name"] for s in stops]
    activities = state.get("activities") or []
    fallback_note = state.get("activity_fallback_note") or ""

    activity_instruction = ""
    if activities:
        activity_stops = [s["name"] for s in stops if s.get("activities")]
        if activity_stops:
            activity_instruction = (
                f" Weave in that this trip was tailored around {', '.join(activities)} — "
                f"highlight {', '.join(activity_stops[:2])} as the activity-matched stops."
            )
    fallback_instruction = f" Note: {fallback_note}" if fallback_note else ""

    prompt = (
        f"Write a warm, engaging 3–4 sentence narrative introducing this day trip to "
        f"{state['city']}. The approved stops for today are: {', '.join(stop_names)}."
        f"{activity_instruction}{fallback_instruction} "
        "Mention only stops from this list — do not mention any other places. "
        "Do not use bullet points or markdown headers."
    )
    response = llm.invoke([HumanMessage(content=prompt)])
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
