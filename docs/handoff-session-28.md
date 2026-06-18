# Session 28 Handoff — RouteIQ Day Trip Planner

**Date:** 2026-06-17
**Branch:** `feature/routeiqagent`
**Tests:** 213 passing (was 198 — added 15 new)

---

## What We Did This Session

### 1. Ratings API investigation & LLM synthetic fallback

Both live rating APIs are dead for now:

| Provider | Status | Root cause |
|---|---|---|
| TripAdvisor | 403 IAM deny | Account-level policy block; try emailing `developer-support@tripadvisor.com` with key UUID + 403 response, or check for pending ToS/verification step at tripadvisor.com/developers |
| Foursquare v3 | 410 Gone | Entire `api.foursquare.com/v3/places/search` endpoint retired platform-wide |
| Foursquare v2 | 402 Credits exhausted | Free tier only gives search (name+location), not venue details (ratings/tips/hours) |

**Built:** `routeiq/ratings/llm_synthetic.py` — `LLMSyntheticRatingProvider`
- Calls the configured LLM in one batch call with POI names + Wikipedia descriptions
- Returns realistic ratings (3.8–4.9), review counts, 2–3 review snippets, hours
- Disk-cached per city (`cache/ratings/llm_synthetic_{city}.json`), 21-day TTL
- Incremental: only sends missing POIs to LLM if cache partially covers input
- Handles markdown fences and LLM failure gracefully (returns null fields)
- Wired into `RatingsFactory` via `RATING_PROVIDER=llm_synthetic`
- `.env` has one-line switch comment: change `RATING_PROVIDER=tripadvisor` once TA key activates

**Tests:** `tests/ratings/test_llm_synthetic.py` — 12 tests (enrich, cache hit/miss/stale/incremental, LLM failure, markdown fence stripping)

### 2. `search_poi_by_name` tool — named place refinement

**Built:** `routeiq/agent/tools/search_poi_by_name.py`
- Nominatim (OpenStreetMap geocoder) — free, no API key, 1 req/sec limit
- Takes `name` + `city`, returns a POI dict with lat/lon, category, osm_id, wikipedia_tag
- Wired into `ALL_TOOLS` and `_TOOL_TO_STEP` map
- **How it works:** LLM reads the tool docstring and decides to call it when user types "add Lombard Street" in the refine box — pure ReAct, no hardcoded parsing

Test it:
```python
from routeiq.agent.tools.search_poi_by_name import search_poi_by_name
search_poi_by_name.invoke({"name": "Lombard Street", "city": "San Francisco, CA"})
# → {"name": "Lombard Street", "lat": 37.8021, "lon": -122.4187, "subtype": "attraction", "wikipedia_tag": "en:Lombard Street (San Francisco)"}
```

### 3. Route animation — matched Route Planner style

**Fixed:** `_render_dt_map()` in `app.py` — AntPath now uses same params as `MapBuilder`:
- `delay=800` (was: default fast)
- `weight=5` (was: 4)
- `pulse_color="#ffffff"` (was: none)
- `dash_array=[10, 20]` (was: none)
- Straight-line fallback PolyLine also bumped: `weight=5`, `opacity=0.75`, `dash_array="10 15"`

### 4. Refine UX improvements

- **Refine hints caption** below the feedback input — shows example refinements:
  `Add Lombard Street · Skip museums · More nature spots · Start at 10 AM · Fewer stops · Include the Ferry Building`
- **City hints caption** below the city input — ⚡ Instant (Bay Area) vs 🌐 First use ~30s (other cities)

### 5. Graceful OverpassUnavailableError

`_expand_kg_for_city` now catches `OverpassUnavailableError` and shows `st.warning()` instead of crashing. The agent still runs — `search_poi_by_name` lets users add specific landmarks manually.

---

## Current `.env` State

```
RATING_PROVIDER=llm_synthetic          # active — works offline
TRIPADVISOR_API_KEY=01d493ac-...       # 403; flip RATING_PROVIDER=tripadvisor once active
FOURSQUARE_API_KEY=fsq3E9q...          # v3 endpoint retired (410)
FOURSQUARE_CLIENT_ID=1QIV...           # v2 — free tier lacks ratings (402)
FOURSQUARE_CLIENT_SECRET=AQ2Z...
```

---

## File Map (new/changed this session)

| File | Change |
|---|---|
| `routeiq/ratings/llm_synthetic.py` | **NEW** — LLM synthetic provider |
| `routeiq/ratings/factory.py` | Added `llm_synthetic` branch |
| `routeiq/ratings/__init__.py` | Exports `LLMSyntheticRatingProvider` |
| `routeiq/agent/tools/search_poi_by_name.py` | **NEW** — Nominatim geocoder tool |
| `routeiq/agent/tools/__init__.py` | Added `search_poi_by_name` to `ALL_TOOLS` |
| `routeiq/agent/day_trip_agent.py` | Added `search_poi_by_name` to `_TOOL_TO_STEP` |
| `app.py` | Route animation params, refine hints, city hints, graceful Overpass error |
| `tests/ratings/test_llm_synthetic.py` | **NEW** — 12 tests |
| `tests/ratings/test_factory.py` | Added `llm_synthetic` factory test |
| `.env` | Cleaned up duplicate RATING_PROVIDER; active = llm_synthetic |

---

## Open Work (Next Session)

### High priority
- **Demo recording** — re-record full flow: city input → live stepper → draft (map + cards) → refine ("add Lombard Street") → approve → done view (map + cards + narrative)
- **TripAdvisor activation** — email developer support or check portal for verification step; once active, 1-line switch in `.env`

### Medium
- **Google Doc** — merge `docs/agent-architecture.md` + `docs/scope-definition.md` for Week 3 submission
- **LA / non-Bay-Area cities** — Overpass is flaky; pre-seeding a city POI cache for LA would make the demo reliable. Run `_expand_kg_for_city("Los Angeles, CA")` once when Overpass is up and commit the resulting `.json.gz` to `cache/pois/`

### Known gotchas
- `RATING_PROVIDER=llm_synthetic` active — LLM ratings are generated on first planning run per city, then cached. Cards show "AI Insights" as source badge.
- `search_poi_by_name` respects Nominatim 1 req/sec — fine for single lookups in the refine loop
- Foursquare v2 client_id/secret in `.env` but NO adapter supports it yet — v2 endpoint works for search but detail calls (ratings) require paid credits
- TripAdvisor adapter is fully implemented and tested — just needs a working key
