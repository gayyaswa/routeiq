# Week 3 Plan: Day Trip Planner Agent

---

## Design Decisions Log

Running record of every non-obvious architectural decision and the reasoning behind it.
Use this section when writing the Week 3 submission Google Doc.

| # | Decision | Alternatives considered | Why we chose this |
|---|---|---|---|
| 1 | **ReAct agent pattern** (`create_react_agent` / manual tool loop) | Fixed pipeline (Week 2 approach), Plan-and-Execute | ReAct loops naturally over tools and self-corrects; genuinely agentic (not scripted) |
| 2 | **LangGraph `MemorySaver` checkpointer** | In-memory dict, Redis | Zero-infrastructure; enables multi-turn refinement ("add food stops") with full message history |
| 3 | **Human-in-the-loop via `interrupt()`** | Post-run approval, no approval step | User sees the draft before narrative is generated; correctable without rerunning the full tool loop |
| 4 | **Foursquare Places API v3** for POI ratings | Google Places (paid), Yelp (restaurants only), TripAdvisor (no free tier) | Free tier (1000 calls/day), global coverage, returns ratings + review snippets + hours |
| 5 | **Batch Foursquare by city+category** (3 calls/city) | Per-POI lookup (80 calls/query) | Stays within free tier; all repeat city queries = 0 API calls from local cache |
| 6 | **ChromaDB semantic similarity for OSM↔Foursquare merge** | rapidfuzz character-level matching, exact name match | Handles name variants ("Alcatraz Island" ↔ "Alcatraz"), abbreviations, and descriptions; reuses existing ChromaDB dependency — no new library needed |
| 7 | **21-day local JSON cache for Foursquare results** | No cache, Redis TTL | Ratings don't change often; 21-day TTL ensures cache outlives any evaluation or demo window so instructors never trigger a live API call |
| 8 | **Strategy pattern for rating provider** (`RATING_PROVIDER` env var) | Hard-coded Foursquare | One-line swap to Google Places or any future provider; `NullRatingProvider` fallback when no key set |

---

## Context

Week 3 requires a true agentic system — not a fixed pipeline. The chosen use case is **"Plan a scenic day in [city]"**. This is genuinely agentic because the agent must:
- Decide *which* stops to visit (not just find stops along a fixed route)
- Order them to minimize travel and respect a time budget
- Loop back and replan when the initial draft doesn't fit
- Refine via conversation ("add food stops", "remove museums")
- Pause for human approval before presenting the final itinerary

The existing Week 2 codebase is a fixed 4-node pipeline. Week 3 adds a second mode: a ReAct agent that wraps the same infrastructure as tools, adds conversation memory, and introduces a human-in-the-loop interrupt.

**Agent one-liner**: My agent helps a traveler plan a full scenic day in any city, replacing 2+ hours of manual TripAdvisor/Google Maps research, using 5 tools to find and enrich POIs, build a time-budgeted itinerary, and pause for human approval before presenting the final plan.

---

## Recommended Approach

### Agent pattern: ReAct with MemorySaver + manual interrupt

```
START → research_agent (tool loop) → draft_complete → INTERRUPT → [approve OR refine → research_agent] → narrate → END
```

- `create_react_agent` (LangGraph prebuilt) handles the tool-calling loop
- `MemorySaver` checkpointer persists conversation across turns (enables "refine" flow)
- After tool loop: agent outputs a structured draft itinerary → `interrupt()` pauses
- In Streamlit: user sees draft itinerary cards + Approve / Refine buttons
- Approve → narrate node runs → map + narrative rendered
- Refine → user types feedback → agent resumes with full history

### What stays from Week 2

- `POIFinder` — reused as core of `find_city_pois` tool (new `find_pois_in_bbox` method added)
- `WikipediaFetcher` — reused as core of `enrich_poi_details` tool
- `NarrativeChain` — reused for final narrative after approval
- `MapBuilder` — reused for rendering the final itinerary map
- `LLMFactory` — unchanged
- All existing tests — must still pass

---

## New files

```
routeiq/ratings/                         # Strategy pattern — pluggable POI rating providers
  __init__.py                            # re-exports POIRatingProvider, RatedPOI, RatingsFactory
  base.py                                # POIRatingProvider ABC + RatedPOI dataclass
                                         #   RatedPOI: poi, rating, review_count, review_snippets, hours
                                         #   ABC method: enrich(poi: POI) -> RatedPOI
  foursquare.py                          # FoursquareRatingProvider(POIRatingProvider)
                                         #   Uses Foursquare Places API (free, 1000 calls/day)
                                         #   Env: FOURSQUARE_API_KEY
                                         #   BATCH strategy: search by city+category (1 call → 50 results)
                                         #     NOT per-POI lookup (would burn 50-100 calls/query)
                                         #   Cache: writes to cache/ratings/foursquare_{city}_{cat}.json
                                         #     TTL: 7 days — ratings don't change often
                                         #     Cache-first: all future queries for same city = 0 API calls
                                         #   Merges with OSM POIs via fuzzy name match or ≤100m proximity
  google_places.py                       # GooglePlacesRatingProvider(POIRatingProvider)
                                         #   Stub — raises NotImplementedError with setup instructions
                                         #   Ready to implement when GOOGLE_PLACES_API_KEY is set
  factory.py                             # RatingsFactory.create() → reads RATING_PROVIDER env var
                                         #   "foursquare" → FoursquareRatingProvider (default)
                                         #   "google"     → GooglePlacesRatingProvider
                                         #   Graceful: if key missing → NullRatingProvider (no enrichment)

routeiq/agent/
  __init__.py
  agent_state.py        # DayTripState TypedDict (messages, city, preferences,
                        #   time_budget_hours, start_time, draft_itinerary, approved)
  day_trip_agent.py     # Builds and returns compiled LangGraph agent graph
                        #   Nodes: research_agent, tools, draft_review, narrate
                        #   Checkpointer: MemorySaver
                        #   interrupt_before=["draft_review"]
                        #   Takes ratings_provider as injected dependency

  tools/
    __init__.py               # re-exports all tool functions
    find_city_pois.py         # @tool find_city_pois(city, categories) → JSON list of POIs
                              #   wraps POIFinder.find_pois_in_bbox() after geocoding city
    rate_pois.py              # @tool rate_pois(poi_json_list) → rated + ranked JSON list
                              #   delegates to injected POIRatingProvider
                              #   filters rating < 3.8 or review_count < 20
                              #   composite score: 0.4*rating + 0.3*log(reviews) + 0.3*scenic_bonus
    get_travel_time.py        # @tool get_travel_time(lat1, lon1, lat2, lon2) → minutes (haversine)
    enrich_poi_details.py     # @tool enrich_poi_details(poi_name, city) → description + image_url
                              #   wraps WikipediaFetcher (factual background, kept separate from ratings)
    estimate_visit.py         # @tool estimate_visit_duration(category, subtype) → minutes
                              #   heuristic dict: museum=90, viewpoint=30, beach=60, etc.

routeiq/insights/prompts/
  day_trip_planner.py   # DAY_TRIP_PLANNER_PROMPT_V1 (active alias: DAY_TRIP_PLANNER_PROMPT)
                        #   System: scenic travel expert, time-aware, uses tools deliberately
                        #   Instructions: find POIs → rate+rank → enrich top 8 → order by proximity
                        #     → check time budget → output structured JSON draft itinerary
```

---

## Foursquare API optimization: Batch search + cache

**Problem**: Naive per-POI Foursquare lookups = 50-100 calls/query → blows through 1000/day limit fast.

**Solution**: Batch search by city + category (1 call returns 50 results), then cache results locally.

```
Naive:    OSM returns 80 POIs → 80 Foursquare lookups = 80 calls/query ❌

Smarter:  Foursquare search: "top places in SF, natural"  → 1 call, 50 results → cached
          Foursquare search: "top places in SF, historic" → 1 call, 50 results → cached
          Foursquare search: "top places in SF, tourism"  → 1 call, 50 results → cached
          Total: 3 calls per city. All repeat SF queries = 0 calls ✅
```

Merge strategy: cross-reference Foursquare results with OSM POIs by fuzzy name match or ≤100m proximity.

```
cache/ratings/                         # auto-generated, gitignored
  foursquare_san_francisco_natural.json
  foursquare_san_francisco_historic.json
  ...                                  # one file per (city, category), 7-day TTL

scripts/
  seed_ratings_cache.py               # pre-seeds cache for all demo cities (~15 Foursquare calls total)
                                      # run once before demo: python3 scripts/seed_ratings_cache.py
```

### Call budget

| Scenario | Foursquare API calls |
|---|---|
| First query for a new city | 3 (one per category: natural, historic, tourism) |
| Any repeat query for cached city | 0 |
| Full demo (5 Bay Area cities, pre-seeded) | 0 live calls |
| 7-day cache expiry refresh | 3 per city |
| Daily budget headroom | ~1000 − (3 × new cities) per day |

---

## Changes to existing files

**`routeiq/graph/poi_finder.py`**
- Add `find_pois_in_bbox(south: float, north: float, west: float, east: float) -> list[POI]`
- Reuses existing `_query_overpass` + cache logic; takes bbox directly instead of deriving from route coords

**`app.py`**
- Add a Streamlit tab: "Day Trip Planner" alongside existing "Route Planner" tab
- Multi-turn chat input (`st.chat_input`)
- Progress stream shows tool calls as they happen (find → rate → enrich → plan)
- After interrupt: renders draft itinerary as time-slotted cards + Approve/Refine buttons
- Resume logic: if approved → `agent.invoke(Command(resume=True))` → narrate + map
- If refine → append user message → agent resumes with full history

**`requirements.txt`**
- Add `rapidfuzz>=3.0.0` (for fuzzy name matching in merge step)
- Foursquare REST calls go through `requests` (already in requirements)

**`.env.example`**
- Add `FOURSQUARE_API_KEY=` and `RATING_PROVIDER=foursquare`
- Add `# GOOGLE_PLACES_API_KEY=` and `# RATING_PROVIDER=google` (commented, future)

---

## Draft itinerary format (agent output at interrupt)

```json
{
  "city": "San Francisco",
  "start_time": "9:00 AM",
  "total_hours": 7.5,
  "stops": [
    {
      "order": 1,
      "name": "Golden Gate Park",
      "category": "natural",
      "arrive": "9:00 AM",
      "depart": "10:30 AM",
      "visit_min": 90,
      "travel_to_next_min": 15,
      "rating": 4.8,
      "review_count": 15234,
      "review_snippet": "Best place to see fog roll in over the city",
      "why_visit": "Expansive park with botanical gardens and buffalo paddock",
      "image_url": "https://..."
    }
  ]
}
```

---

## Tests to add

```
tests/agent/
  test_tools.py           # unit test each tool function (mock POIFinder/WikipediaFetcher)
  test_day_trip_agent.py  # integration test: full agent run with MemorySaver, verify interrupt fires
tests/ratings/
  test_foursquare.py      # unit test FoursquareRatingProvider (mock HTTP, test cache hit/miss)
  test_factory.py         # test RatingsFactory env var routing
```

Existing 127 tests must still pass (`python3 -m pytest tests/ -v`).

---

## Verification

1. `python3 -m pytest tests/ -v` — all 127 + new tests pass
2. `streamlit run app.py` → "Day Trip Planner" tab visible
3. Type: "Plan a scenic day in San Francisco — I love nature and history, 8 hours starting at 9am"
4. Verify: agent calls `find_city_pois` → `rate_pois` → `enrich_poi_details` → `estimate_visit_duration` in tool loop
5. Verify: draft itinerary cards appear with ratings + review snippets + Approve/Refine buttons (interrupt fired)
6. Click Approve → verify narrative + folium map renders
7. Type "Remove museums, add more nature" → verify agent refines and shows updated draft
8. Verify conversation memory persists (agent references prior preferences in follow-up)
9. Verify Foursquare cache: second run for same city shows 0 API calls in logs

---

## Scope boundary (what's NOT in this plan)

- Multi-day itineraries
- Real-time pricing or ticketing
- Hotel/restaurant booking
- Offline support or export
- LangSmith tracing (defer to later)
- Yelp integration (restaurants only, low priority)
