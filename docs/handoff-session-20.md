# RouteIQ — Session 20 Handoff

**Date:** 2026-06-15
**Status:** Week 3 architecture documented. Code build started — NO code committed yet.

---

## What happened this session

- Confirmed Foursquare API key is in `.env` (`FOURSQUARE_API_KEY` + `RATING_PROVIDER=foursquare`)
- Created `docs/agent-architecture.md` — full Week 3 architecture + design decisions table (use for Google Doc submission)
- Updated `docs/plan-week3-agent.md` — added Design Decisions Log table at the top
- Updated memory: `architecture_decisions.md` — added all Week 3 agent decisions
- Key design decision made: **ChromaDB semantic similarity for OSM↔Foursquare merge** (instead of rapidfuzz) — reuses existing dep, handles name variants like "Alcatraz Island" ↔ "Alcatraz"
- Key TTL decision: **21-day Foursquare cache** (up from 7 days) — ensures instructors never trigger live API calls during evaluation

No source code was written or committed this session (all code writes were rejected mid-session).

---

## Exact state of code

- Branch: `feature/routeiqagent`
- Last commit: `2f8c65a` (unchanged from Session 19)
- **0 new .py files written** — all planning/docs only
- 127 tests still passing (unchanged)
- `cache/ratings/` directory exists but is empty

---

## What to build next session (in order)

### Phase 1 — Ratings layer

Create these files from scratch (none exist yet):

**`routeiq/ratings/base.py`**
```python
from dataclasses import dataclass
from abc import ABC, abstractmethod
from routeiq.graph.poi import POI

@dataclass
class RatedPOI:
    poi: POI
    rating: float | None = None      # 0–5.0 normalized
    review_count: int | None = None
    review_snippet: str | None = None
    hours: str | None = None

class POIRatingProvider(ABC):
    @abstractmethod
    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]: ...
```

**`routeiq/ratings/foursquare.py`** — `FoursquareRatingProvider`:
- `enrich_batch(city, pois)`: fetch 3 categories → build ephemeral ChromaDB index → similarity merge
- `_fetch_category(city, cat)`: check 21-day cache first, else call API
- `_call_api(city, cat)`: `GET https://api.foursquare.com/v3/places/search` with `Authorization: {API_KEY}` header (NOT Bearer — Foursquare v3 uses raw key)
- `_build_index(fs_pool)`: `chromadb.EphemeralClient()` → `create_collection("fs_merge")` → `add(documents=[names], ids=[str(i)])`
- `_find_match(poi, fs_pool, collection)`: `collection.query(query_texts=[poi.name], n_results=1)` → distance ≤ 0.6 → return `fs_pool[idx]`; else proximity fallback ≤ 100 m
- Foursquare rating is out of 10 → divide by 2 to normalize to 0–5
- Cache TTL: **21 days** (not 7)
- Cache path: `cache/ratings/foursquare_{safe_city}_{category}.json`

**`routeiq/ratings/google_places.py`** — stub, raises `NotImplementedError`

**`routeiq/ratings/factory.py`** — `RatingsFactory.create()`:
- Reads `RATING_PROVIDER` env var (`"foursquare"` default)
- If key missing → returns `_NullRatingProvider` (passes POIs through with `None` quality fields)

**`routeiq/ratings/__init__.py`** — re-exports `POIRatingProvider`, `RatedPOI`, `RatingsFactory`

**Tests:**
- `tests/ratings/__init__.py`
- `tests/ratings/test_foursquare.py` — mock `requests.get`; test cache hit (no HTTP), cache miss (writes file), name similarity merge, proximity fallback, rating normalization (÷2)
- `tests/ratings/test_factory.py` — env var routing; no key → NullRatingProvider

**`routeiq/graph/poi_finder.py`** — add method:
```python
def find_pois_in_bbox(self, south: float, north: float, west: float, east: float) -> list[POI]:
    """Find POIs within a lat/lon bounding box — used by the Day Trip agent."""
    from shapely.geometry import box
    bbox_poly = box(west, south, east, north)
    # Path 1: master cache
    if os.path.exists(self._master_path):
        result = self._filter_master(bbox_poly, time.perf_counter())
        if result is not None:
            return result
    # Path 2: per-bbox cache
    stem = f"pois_n{north:.3f}_s{south:.3f}_e{east:.3f}_w{west:.3f}"
    gz_path = os.path.join(self._cache_dir, f"{stem}.json.gz")
    if os.path.exists(gz_path):
        with gzip.open(gz_path, "rb") as f:
            return [POI(**d) for d in json.loads(f.read())]
    # Path 3: Overpass
    return self._query_overpass(bbox_poly, gz_path, None, time.perf_counter())
```

**`requirements.txt`** — no new dependencies (rapidfuzz was dropped; ChromaDB already present)

**`.env.example`** — add at end:
```
FOURSQUARE_API_KEY=
RATING_PROVIDER=foursquare
```

---

### Phase 2 — Agent tools

Create directories: `routeiq/agent/`, `routeiq/agent/tools/`, `tests/agent/`

**`routeiq/agent/agent_state.py`**:
```python
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class DayTripState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    city: str
    preferences: list[str]
    time_budget_hours: float
    start_time: str
    draft_itinerary: dict | None
    approved: bool
    narrative: str | None
```

**5 tool files** (`@tool` decorator from `langchain_core.tools`):

1. **`find_city_pois.py`** — `find_city_pois(city, categories)`:
   - `ox.geocode_to_gdf(city)` → `.total_bounds` → `(west, south, east, north)`
   - `POIFinder().find_pois_in_bbox(south, north, west, east)`
   - Filter to requested categories, return `json.dumps([dataclasses.asdict(p) for p in pois[:100]])`

2. **`rate_pois.py`** — `rate_pois(city, poi_list_json)`:
   - Deserialize → `RatingsFactory.create().enrich_batch(city, pois)`
   - Filter: skip if `rating < 3.8` AND `review_count < 20` (only filter if BOTH fail; missing rating = include)
   - Composite score: `0.4*(rating/5) + 0.3*log1p(reviews)/log1p(10000) + 0.3*(0.1 if wikipedia_tag else 0)`
   - Return top 30 sorted by score descending

3. **`get_travel_time.py`** — `get_travel_time(lat1, lon1, lat2, lon2)`:
   - Haversine → km; minutes at 30 km/h + 5 min overhead
   - Return `json.dumps({"distance_km": ..., "estimated_minutes": ...})`

4. **`enrich_poi_details.py`** — `enrich_poi_details(poi_name, city)`:
   - Create temp `POI(name=poi_name, ...)` → `WikipediaFetcher().enrich(poi)`
   - Return `json.dumps({"description": poi.description, "image_url": poi.image_url})`

5. **`estimate_visit.py`** — `estimate_visit_duration(category, subtype)`:
   - Lookup table: `museum→90, viewpoint→30, beach→60, park→60, ruins→45, monument→20, lighthouse→25, castle→60, waterfall→30, aquarium→90, winery→60, zoo→120`; default 45
   - Return `json.dumps({"estimated_minutes": N})`

**`routeiq/agent/tools/__init__.py`** — re-exports all 5 tools as a list `ALL_TOOLS`
**`routeiq/agent/__init__.py`** — re-exports `DayTripState`, `build_day_trip_graph`
**`tests/agent/__init__.py`, `tests/agent/test_tools.py`**

---

### Phase 3 — Agent graph + prompt

**`routeiq/insights/prompts/day_trip_planner.py`** — `DAY_TRIP_PLANNER_PROMPT_V1`:
- System: "You are a scenic travel expert. Plan a full-day itinerary using your tools."
- Instructions: (1) find_city_pois, (2) rate_pois to filter+rank, (3) enrich top 8, (4) estimate_visit_duration + get_travel_time for schedule, (5) output structured JSON draft with city/start_time/total_hours/stops[]
- Each stop: order, name, category, arrive, depart, visit_min, travel_to_next_min, rating, review_count, review_snippet, why_visit, image_url

**`routeiq/agent/day_trip_agent.py`** — `build_day_trip_graph(llm, ratings_provider=None)`:
```
Nodes: plan, review, narrate
plan: manual ReAct loop (llm.bind_tools(ALL_TOOLS) + while tool_calls loop)
review: calls interrupt(state["draft_itinerary"]) — pauses graph
narrate: calls NarrativeChain on top stops from approved draft
Edges: START→plan→review; review→narrate (approved) or →plan (refine)
Checkpointer: MemorySaver()
```

**`tests/agent/test_day_trip_agent.py`** — mock LLM, verify interrupt fires, verify resume reaches narrate

---

### Phase 4 — UI + seed script

**`app.py`** — wrap existing content in `tab1, tab2 = st.tabs(["Route Planner", "Day Trip Planner"])`:
- `tab1` = all existing code (unchanged)
- `tab2` = Day Trip Planner:
  - `st.chat_input` for multi-turn
  - `st.chat_message` for history display
  - `st.spinner` + tool call expander while agent runs
  - When `__interrupt__` in stream → show draft itinerary time-slotted cards
  - Approve button → `graph.invoke(Command(resume={"approved": True}), config=...)`
  - Refine text + button → `graph.invoke(Command(resume={"approved": False, "feedback": text}), config=...)`
  - After approval → narrative + folium map

**`scripts/seed_ratings_cache.py`** — pre-seeds 5 demo cities × 3 categories = 15 Foursquare calls:
```python
DEMO_CITIES = ["San Francisco, CA", "Napa, CA", "San Jose, CA",
               "Half Moon Bay, CA", "Sausalito, CA"]
```

---

## Key files to reference

- `docs/agent-architecture.md` — full architecture + design decisions (use for submission doc)
- `docs/plan-week3-agent.md` — implementation plan with decisions log
- `routeiq/graph/poi_finder.py` — add `find_pois_in_bbox` here
- `routeiq/rag/wikipedia_fetcher.py` — `WikipediaFetcher.enrich(poi)` mutates in place
- `routeiq/insights/narrative_chain.py` — reuse in narrate node
- `routeiq/llm_factory.py` — create ChatAnthropic here

## Foursquare API notes

- Auth header: `"Authorization": API_KEY` (raw key, NOT "Bearer KEY" — Foursquare v3 specific)
- Search endpoint: `https://api.foursquare.com/v3/places/search`
- Fields param: `"name,geocodes,rating,stats,hours,tips"`
- Rating scale: 0–10 → divide by 2 to normalize to 0–5
- `stats.total_ratings` = review count (primary); `stats.total_tips` = fallback

## Verification checklist (run at end of next session)

1. `python3 -m pytest tests/ -v` — all 127 + new tests pass
2. `streamlit run app.py` → two tabs: "Route Planner" | "Day Trip Planner"
3. Route Planner tab: existing demo routes still work
4. Day Trip Planner: "Plan a scenic day in San Francisco — I love nature and history, 8 hours starting at 9am"
5. Verify tool calls stream, draft itinerary appears with Approve/Refine
6. Approve → narrative + map
7. "Remove museums, add more nature" → agent refines
8. `ls cache/ratings/` → JSON files present
