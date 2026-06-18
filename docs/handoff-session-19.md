# RouteIQ — Session 19 Handoff

**Date:** 2026-06-15  
**Status:** Week 3 planning complete. Ready to build.

---

## What happened this session

- Read Week 3 handout (`docs/Week 3 Project Handout_ Agentic AI Systems.md`)
- Decided on use case: **"Plan a scenic day in [city]"** — city-wide day trip itinerary planner
- Designed full agent architecture: ReAct agent, MemorySaver, human-in-the-loop interrupt
- Designed POI quality enrichment: Foursquare ratings (Strategy pattern, pluggable to Google Places)
- Designed Foursquare API optimization: batch search + local cache (3 calls/city, 0 on repeat)
- Wrote full plan to `docs/plan-week3-agent.md`

No code was written this session — planning only.

---

## The Week 3 use case

**Input**: "Plan a scenic day in San Francisco — I love nature and history, 8 hours starting at 9am"

**Agent flow**:
1. `find_city_pois(city, categories)` — OSM POIs in city bbox (wraps existing POIFinder)
2. `rate_pois(poi_list)` — Foursquare batch ratings (3 API calls/city, cached 7 days)
3. `enrich_poi_details(poi_name)` — Wikipedia description + image (wraps existing WikipediaFetcher)
4. `estimate_visit_duration(category)` — heuristic minutes per stop
5. `get_travel_time(lat1, lon1, lat2, lon2)` — haversine between stops
6. Agent orders stops, checks time budget, loops if needed
7. **INTERRUPT** — user sees draft itinerary with Approve/Refine buttons
8. After approval → NarrativeChain + MapBuilder render final output

**Memory**: LangGraph MemorySaver — user can say "add food stops" and agent retains context

---

## Key architecture decisions (locked)

| Decision | Choice | Reason |
|---|---|---|
| Agent pattern | ReAct (`create_react_agent`) | Tool loop with decision-making |
| Memory | LangGraph `MemorySaver` | Enables multi-turn refinement |
| Human-in-the-loop | `interrupt_before=["draft_review"]` | User approves before narrative |
| Rating provider | Foursquare (Strategy pattern) | Free, pluggable to Google Places |
| Foursquare strategy | Batch search + local cache | 3 calls/city vs 80 calls/query |
| Cache location | `cache/ratings/foursquare_{city}_{cat}.json` | Same pattern as existing POI cache |
| Provider swap | `RATING_PROVIDER` env var | No code change to swap providers |
| POI merge | Fuzzy name match or ≤100m proximity | Cross-reference OSM + Foursquare |

---

## New files to create (in order)

```
Phase 1 — Ratings layer (no LLM needed, testable first):
  routeiq/ratings/base.py                  # POIRatingProvider ABC + RatedPOI dataclass
  routeiq/ratings/foursquare.py            # FoursquareRatingProvider (batch + cache)
  routeiq/ratings/google_places.py         # GooglePlacesRatingProvider (stub)
  routeiq/ratings/factory.py               # RatingsFactory
  routeiq/ratings/__init__.py
  tests/ratings/test_foursquare.py
  tests/ratings/test_factory.py

Phase 2 — Agent tools:
  routeiq/agent/agent_state.py             # DayTripState TypedDict
  routeiq/agent/tools/find_city_pois.py
  routeiq/agent/tools/rate_pois.py
  routeiq/agent/tools/get_travel_time.py
  routeiq/agent/tools/enrich_poi_details.py
  routeiq/agent/tools/estimate_visit.py
  routeiq/agent/tools/__init__.py
  tests/agent/test_tools.py

Phase 3 — Agent graph + prompt:
  routeiq/insights/prompts/day_trip_planner.py
  routeiq/agent/day_trip_agent.py
  routeiq/agent/__init__.py
  tests/agent/test_day_trip_agent.py

Phase 4 — UI + scripts:
  app.py (add "Day Trip Planner" tab)
  scripts/seed_ratings_cache.py
```

## Existing files to modify

- `routeiq/graph/poi_finder.py` — add `find_pois_in_bbox(south, north, west, east)` method
- `app.py` — add "Day Trip Planner" tab (multi-turn chat, interrupt UI, Approve/Refine buttons)
- `requirements.txt` — add `rapidfuzz>=3.0.0`
- `.env.example` — add `FOURSQUARE_API_KEY`, `RATING_PROVIDER`

---

## What to do next session

1. **Get Foursquare API key** (free at foursquare.com/developers) — add to `.env`
2. Start with Phase 1: build `routeiq/ratings/` layer first (most novel, most testable independently)
3. Run `python3 -m pytest tests/ -v` at the end of each phase to confirm no regressions

---

## Repo state at handoff

- Branch: `main`  
- Last commit: `2f8c65a` — docs: document POI cache seeding for out-of-area routes
- All 127 tests passing (last verified Session 14)
- No uncommitted code changes (only binary ChromaDB files + untracked POI caches)

---

## Full plan

See `docs/plan-week3-agent.md` for the complete implementation plan.
