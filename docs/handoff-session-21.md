# RouteIQ — Session 21 Handoff

**Date:** 2026-06-16
**Branch:** `feature/routeiqagent`
**Tests:** 166 passing (was 127 at start of Week 3)
**Status:** Phase 1 (ratings layer) + Phase 2 (KG methods + agent tools) COMPLETE.
Phase 3 (agent graph + prompt) + Phase 4 (UI + seed script) remain.

---

## What was built this session

### Phase 1 — Ratings layer (complete)

| File | What |
|---|---|
| `routeiq/ratings/base.py` | `RatedPOI` dataclass + `POIRatingProvider` ABC (was already there) |
| `routeiq/ratings/foursquare.py` | `FoursquareRatingProvider`: 3-bucket city sweep, 21-day JSON cache, ChromaDB name merge + 100 m proximity fallback, rating ÷2 normalization |
| `routeiq/ratings/google_places.py` | Stub — raises `NotImplementedError` |
| `routeiq/ratings/factory.py` | `RatingsFactory.create()` reads `RATING_PROVIDER` env var; no key → `_NullRatingProvider` |
| `routeiq/ratings/__init__.py` | Re-exports `POIRatingProvider`, `RatedPOI`, `RatingsFactory` |
| `routeiq/graph/poi_finder.py` | Added `find_pois_in_bbox(south, north, west, east)` — same 3-path lookup as `find_pois()` |
| `.env.example` | Uncommented `FOURSQUARE_API_KEY` + `RATING_PROVIDER=foursquare` |
| `tests/ratings/test_foursquare.py` | 10 tests: cache hit/miss/stale, rating ÷2, name merge, proximity fallback |
| `tests/ratings/test_factory.py` | 6 tests: env var routing, no key → null, unknown → null |

**Key gotcha:** `chromadb.EphemeralClient()` is a process-level singleton — reusing a fixed
collection name causes `InternalError: Collection already exists`. Fixed with `uuid4().hex` suffix.

### Phase 2 — KG methods + agent tools (complete)

**`routeiq/graph/knowledge_graph.py`** — 4 new methods:
- `known_cities() -> set[str]` — city node names
- `get_pois_for_city(city_name) -> list[POI]` — strips ", CA" suffix, walks LOCATED_IN edges
- `add_city_pois(city_name, lat, lon, pois)` — dynamic city expansion; idempotent
- `_add_near_poi_edges_for(pois)` — NEAR_POI edges among new-city POIs only

**`routeiq/agent/`** — new package:
- `agent_state.py` — `DayTripState` TypedDict for LangGraph
- `tools/find_city_pois.py` — KG lookup; no OSMnx inside tool
- `tools/rate_pois.py` — Foursquare enrich + composite score → top 30
- `tools/get_travel_time.py` — haversine point-to-point, 30 km/h + 5 min overhead
- `tools/enrich_poi_details.py` — `WikipediaFetcher().enrich()` on temp POI
- `tools/estimate_visit.py` — subtype lookup table, 45 min default
- `tools/__init__.py` — exports `ALL_TOOLS` list
- `__init__.py` — re-exports `DayTripState`

**Tests:**
- `tests/test_knowledge_graph.py` — 8 new tests for KG methods
- `tests/agent/test_tools.py` — 14 tests covering all 5 tools

**Key gotcha:** `__init__.py`'s `from routeiq.agent.tools.X import X` shadows the submodule
name. `patch("routeiq.agent.tools.X.ClassName")` resolves to the StructuredTool object, not
the module. Always use `patch.object(sys.modules["routeiq.agent.tools.X"], "ClassName")`.

**Key design decision:** `find_city_pois` uses KG-first (not OSMnx geocode). For non-Bay-Area
cities, `app.py` runs a pre-flight before the agent starts — fetches Overpass, calls
`kg.add_city_pois()`, then starts agent. Single clean tool path.

---

## What to build next session (Phase 3 + 4)

### Phase 3 — Agent graph + prompt

**`routeiq/insights/prompts/day_trip_planner.py`** — `DAY_TRIP_PLANNER_PROMPT_V1`:
- System: "You are a scenic travel expert. Plan a full-day itinerary using your tools."
- Tool call order: (1) find_city_pois, (2) rate_pois, (3) enrich top 8, (4) estimate_visit + get_travel_time for schedule, (5) output structured JSON draft
- Draft JSON shape:
  ```json
  {
    "city": "San Francisco, CA",
    "start_time": "9:00 AM",
    "total_hours": 8,
    "stops": [
      {
        "order": 1, "name": "...", "category": "...",
        "arrive": "9:00 AM", "depart": "10:30 AM",
        "visit_min": 90, "travel_to_next_min": 15,
        "rating": 4.5, "review_count": 5000,
        "review_snippet": "...", "why_visit": "...",
        "image_url": "...", "lat": 37.82, "lon": -122.42
      }
    ]
  }
  ```

**`routeiq/agent/day_trip_agent.py`** — `build_day_trip_graph(llm, ratings_provider=None)`:
```
Nodes: plan, review, narrate
plan:    manual ReAct loop — llm.bind_tools(ALL_TOOLS) + while tool_calls: execute → append
review:  interrupt(state["draft_itinerary"]) — graph pauses
narrate: NarrativeChain on top stops from approved draft → sets state["narrative"]
Edges:   START→plan→review; review→narrate (approved=True) or →plan (feedback)
Checkpointer: MemorySaver()
```

**`routeiq/agent/__init__.py`** — add re-export of `build_day_trip_graph`

**`tests/agent/test_day_trip_agent.py`**:
- Mock LLM that returns tool call then draft JSON
- Verify interrupt fires in review node
- Verify resume(approved=True) reaches narrate
- Verify resume(approved=False, feedback="...") loops back to plan

### Phase 4 — UI + seed script

**`app.py`** — wrap existing content in two tabs:
```python
tab1, tab2 = st.tabs(["Route Planner", "Day Trip Planner"])
```
- `tab1` = all existing code unchanged
- `tab2` = Day Trip Planner:
  - City + preferences + hours + start_time inputs (sidebar or inline)
  - **Pre-flight block**: check `kg.known_cities()` → spinner + `kg.add_city_pois()` if new city
  - `st.chat_input` + `st.chat_message` for conversation history
  - `st.spinner` + tool call expander while agent runs
  - When `__interrupt__` in stream → render draft itinerary as time-slotted stop cards
  - **Approve button** → `graph.invoke(Command(resume={"approved": True}), config=...)`
  - **Refine text + button** → `graph.invoke(Command(resume={"approved": False, "feedback": text}), config=...)`
  - After approval → narrative prose + Folium map with stop markers

**`scripts/seed_ratings_cache.py`** — pre-seed 5 demo cities × 3 categories = 15 Foursquare calls:
```python
DEMO_CITIES = ["San Francisco, CA", "Napa, CA", "San Jose, CA",
               "Half Moon Bay, CA", "Sausalito, CA"]
```

---

## Key files to reference

| File | Why |
|---|---|
| `routeiq/agent/tools/__init__.py` | `ALL_TOOLS` list — pass to `llm.bind_tools()` |
| `routeiq/agent/agent_state.py` | `DayTripState` — shared graph state shape |
| `routeiq/insights/narrative_chain.py` | Reuse in `narrate` node |
| `routeiq/ui/map_builder.py` | Reuse for final itinerary map |
| `routeiq/llm_factory.py` | `create_llm()` — pass result into `build_day_trip_graph(llm)` |
| `routeiq/graph/knowledge_graph.py` | `known_cities()`, `add_city_pois()` for pre-flight |
| `docs/agent-architecture.md` | Full architecture + design decisions for submission doc |

---

## Verification checklist (run at end of next session)

1. `python3 -m pytest tests/ -v` — all 166+ tests pass
2. `streamlit run app.py` → two tabs: "Route Planner" | "Day Trip Planner"
3. Route Planner tab: existing demo routes still work (no regression)
4. Day Trip tab — Bay Area: "Plan a scenic day in San Francisco — nature and history, 8 hours at 9am"
   - No spinner (KG already has SF)
   - Tool calls stream in expander
   - Draft itinerary appears with time slots
   - Approve → narrative + map renders
5. Day Trip tab — non-Bay-Area: "Plan a day in Los Angeles, CA"
   - Spinner: "Fetching POIs for Los Angeles..."
   - After fetch: agent starts, same flow as above
   - Second run: no spinner (KG cached in session)
6. Refine flow: "Remove museums, add more outdoor spots" → agent re-plans
7. `ls cache/ratings/` → JSON files present after first run
8. `python3 scripts/seed_ratings_cache.py` → 15 files in `cache/ratings/`

---

## Git state

- Branch: `feature/routeiqagent`
- Last commit this session: Phase 1 + Phase 2 code (see commit for full list)
- 166/166 tests passing
- Uncommitted next session: Phase 3 + Phase 4 work
