# Handoff — Session 25

**Date:** 2026-06-17
**Branch:** `feature/routeiqagent`
**Tests:** 198/198 passing

---

## What was done this session

### Commit 1 — `9852870` — Live stepper + progress registry (Session 24 dirty files)
Three files that were staged but uncommitted at Session 24 end:
- `routeiq/agent/day_trip_agent.py` — thread-safe progress registry (`register_progress`, `unregister_progress`, `_emit_progress`), `_plan(config)` receives `RunnableConfig` so `thread_id` is available during the ReAct loop for live stepper updates
- `app.py` — `_DT_STEPS` list, `_render_stepper(steps=)` parameterized so both Route Planner and Day Trip share the same stepper renderer; planning poll now shows the live stepper
- `tests/agent/test_day_trip_agent.py` — fixed patch target `_make_llm` → `create_llm`

### Commit 2 — `11ead77` — Real route scheduling + TripAdvisor done view
Main feature work:

**`routeiq/agent/agent_state.py`**
- Added `route_coords: Optional[List[tuple]]` to `DayTripState`

**`routeiq/agent/day_trip_agent.py`**
- `_minutes_to_timestr(total) -> str` — converts minutes-since-midnight to "9:00 AM"
- `_timestr_to_minutes(s) -> Optional[float]` — inverse; returns None on unparseable input
- `_haversine_km(lat1, lon1, lat2, lon2) -> float` — great-circle km, no external deps
- `_TRANSITION_OVERHEAD_MIN = 7.0` — parking + walk to entrance (separate from `visit_duration_min`)
- `_schedule_stops(stops, start_time, time_budget_hours, city) -> (list[dict], list[tuple])`
  - Geocodes city → centroid (lazy `import osmnx as ox`)
  - `GraphLoader().load(lat±0.15, lon±0.15)` — pickle-cached, fast on repeat
  - Nearest-neighbor sort: highest `composite_score` first, then greedy by haversine distance; preserves LLM order when no `composite_score` present
  - `RouteGraph(G).find_route()` per consecutive stop pair → real A* drive times
  - Assigns `arrival_time`/`departure_time` per stop
  - Trims from tail while last stop's departure exceeds budget
  - Graceful fallback: `return original_stops, []` on any exception
- `_plan()` — calls `_schedule_stops` after structured extraction; returns `route_coords` in state dict
- `ItineraryStop.photo_urls` — added faithful `description` field
- Extraction prompt — added CRITICAL instruction to copy `photo_urls`, `rating`, `review_count`, `review_source`, `hours` exactly from `rate_pois` tool output

**`routeiq/ui/card_renderer.py`** — added `render_dt_card(stop, rank) -> str`
- Photo: `photo_urls[0]` → fallback `image_url` → SVG placeholder; `onerror` handler; `riShow()` lightbox
- Layout: category badge + time slot | rank. name | ⭐ rating (count) · source | why_visit (2-line clamp) | visitor_quote (indigo left-border) | activity badges | 🕐 hours

**`routeiq/ui/__init__.py`** — exports `render_dt_card`

**`app.py`**
- `render_dt_card` and `IMAGE_MODAL_HTML` imported at top
- `route_coords: None` added to `initial_state`
- `dt_route_coords` cleared on new plan start
- `route_coords` captured from snapshot when `dt_phase → draft_ready`
- `route_coords` captured from narrate thread result when `dt_phase → done`
- Done view rebuilt: `[map 3/5 | cards 2/5]` layout — AntPath indigo polyline + numbered DivIcon markers + `render_dt_card` cards + trip narrative expander below

**Tests**
- Added `route_coords: None` to `_initial_state()`
- Added `_no_schedule` autouse fixture to `TestInterruptFires`, `TestResumeApproved`, `TestResumeRefine` — patches `_schedule_stops` to `lambda stops, *_: (stops, [])` so existing tests don't hit OSMnx/GraphLoader
- Added `TestScheduleStops` (11 tests): empty input, geocode failure, graph load failure, first stop gets start time, budget trim drops last stop, `_minutes_to_timestr` corner cases, `_timestr_to_minutes` roundtrip + invalid input

### Commit 3 — `f609e95` — Map in draft view, route fallback, unified card renderer
Three bugs fixed:

1. **Route not visible** — `_schedule_stops` falls back to `[]` coords when the city bbox OSM graph isn't cached (always true on first run for a city). Done view was guarded by `if route_coords:` with no fallback, so no line showed. Fix: extracted `_render_dt_map(stops, route_coords, height)` — draws `AntPath` when road coords available, dashed `PolyLine` between stops otherwise. Route order is now always visible.

2. **No map in draft** — `draft_ready`/`narrating` phases only showed cards. Fix: `_render_dt_map` is now called in the shared draft block (above the cards), using `dt_route_coords` from session_state which is already captured from the snapshot by the time `draft_ready` is set.

3. **Images not showing in draft** — Draft used `_dt_stop_card_html` (no `onerror` fallback, no `riShow` lightbox, bare `<img>`). Fix: replaced with `render_dt_card` + `IMAGE_MODAL_HTML` everywhere. Deleted `_dt_stop_card_html`.

4. **Duplicate content in done phase** — `"done"` was still in the shared draft-section condition `if dt_phase in ("draft_ready", "narrating", "done"):`, so the done view rendered old draft cards above its own cards. Removed `"done"` from the condition.

---

## Current architecture — Day Trip Planner flow

```
User fills form → "Plan My Day" button
    → KG pre-flight: unknown city? fetch POIs from Overpass, add_city_pois()
    → _run_dt_planning_thread (background)
        LangGraph graph.stream(initial_state)
            plan node → ReAct loop (find_city_pois, rate_pois, enrich_poi_details, ...)
                      → _emit_progress() → live stepper updates in UI poll
                      → structured extraction (DayTripItinerary)
                      → _schedule_stops() → real A* times + route_coords
            [interrupt before review node]
        result_holder["status"] = "interrupted"
    → UI poll detects thread done
        dt_draft = snapshot.values["draft_itinerary"]
        dt_route_coords = snapshot.values["route_coords"]
        dt_phase = "draft_ready"

draft_ready view:
    Map (AntPath or dashed PolyLine) + numbered markers
    render_dt_card cards (photos, ratings, quotes, times) + IMAGE_MODAL_HTML
    ✅ Approve → _run_dt_narrate_thread → narrate node → narrative
    🔄 Refine → _run_dt_refine_thread → re-runs plan node with feedback

done view:
    [map 3/5 | cards 2/5]
        map: _render_dt_map (AntPath or fallback)
        cards: render_dt_card × N
    Trip narrative expander
```

---

## Key files

| File | Role |
|---|---|
| `routeiq/agent/day_trip_agent.py` | LangGraph graph, `_schedule_stops`, helpers, progress registry |
| `routeiq/agent/agent_state.py` | `DayTripState` TypedDict |
| `routeiq/agent/tools/` | `find_city_pois`, `rate_pois`, `enrich_poi_details`, `get_travel_time`, `estimate_visit_duration` |
| `routeiq/ui/card_renderer.py` | `render_dt_card`, `render_stop_card`, `render_vector_card`, `IMAGE_MODAL_HTML` |
| `routeiq/ratings/` | `TripAdvisorRatingProvider`, `FoursquareRatingProvider`, `RatingsFactory` |
| `app.py` | Two-tab UI; `_render_dt_map`, `_render_stepper`, thread functions |
| `tests/agent/test_day_trip_agent.py` | 198 tests total, incl. `TestScheduleStops` |

---

## Known limitations / next things to address

- **`_schedule_stops` always falls back on first run** — The city bbox OSM graph isn't pre-cached. `GraphLoader` downloads from Overpass on first load (can take 30–60s or time out). The dashed PolyLine fallback is the current UX. Options: (a) pre-cache city graphs at startup alongside KG, (b) run `_schedule_stops` async and update the map after it resolves.

- **Google Doc** — Needs `docs/agent-architecture.md` + `docs/scope-definition.md` merged for Week 3 submission.

- **Demo recording** — Re-record showing: live stepper during planning → draft map with stops → approve → done view with route map + TripAdvisor cards + narrative.

---

## Env vars required

```
LLM_PROVIDER=nebius          # or anthropic
NEBIUS_API_KEY=...
LLM_MODEL=...
NEBIUS_API_BASE=...
TRIPADVISOR_API_KEY=...      # primary ratings
FOURSQUARE_API_KEY=...       # secondary ratings (optional)
RATING_PROVIDER=tripadvisor  # or foursquare
```

## Next session priorities

### 1 — Google Doc (Week 3 submission — highest priority)
Merge `docs/agent-architecture.md` and `docs/scope-definition.md` into the submission Google Doc. Sections needed:

- **Project overview** — what the Day Trip Planner does, why agentic (ReAct loop, interrupt/resume)
- **Architecture diagram** — LangGraph graph nodes → interrupt → UI poll → narrate thread; tool chain: `find_city_pois` → `rate_pois` → `enrich_poi_details`
- **Datasets** — OpenStreetMap (Overpass API, city bbox download), TripAdvisor API (ratings/photos/quotes), Wikipedia (fallback image/description), KG SQLite (POI cache)
- **Prompts used** — link to `prompts.md` entries; highlight extraction prompt (CRITICAL copy-fields instruction) and narrative prompt
- **Iterations / learnings** — KG warm-up → dynamic city expansion → live stepper → TripAdvisor card layout → route fallback
- **Week 3 scope** — what was agentic (interrupt/resume, structured extraction, live progress), what was out of scope (multi-day trips, real-time traffic)

### 2 — Demo recording (re-record this session's work)
Script the golden path: Austin day trip, 6-hour budget

1. Fill form → "Plan My Day" → watch live stepper advance through ReAct steps
2. Draft view loads: dashed PolyLine map (fallback visible) + numbered markers + TripAdvisor cards (photos, ratings, quotes, time slots)
3. Click ✅ Approve → narrating spinner → done view
4. Done view: map + cards side-by-side + trip narrative expander

Known rough edges to call out on-screen (not hide): dashed line instead of road-following route = OSM graph not yet cached for this city.

### 3 — (Optional) Pre-cache city OSM graph at startup
Patch `app.py` `@st.cache_resource` warm-up block (already runs `kg.warm_up()`) to also call `GraphLoader().load(lat±0.15, lon±0.15)` for the default cities (Austin, San Antonio, Houston). This makes `_schedule_stops` succeed on first run → AntPath replaces dashed PolyLine.

Risk: adds ~30–60s to cold startup. Acceptable if the KG warm-up already takes that long. Run them concurrently with `concurrent.futures.ThreadPoolExecutor` if startup time is a concern.

---

## Gotchas

- `@st.cache_resource` holds instances — restart Streamlit after code changes
- `MemorySaver` checkpointer — `thread_id` in `session_state` must match across planning/narrate/refine calls
- `import osmnx as ox` is always lazy (inside function body) — never at module scope
- `composite_score` field comes from `rate_pois` output — already present in stop dicts for the nearest-neighbor sort
- `leg_coord_slices[0]` is always `[]` (no drive before stop 0) — safe because empty list contributes nothing to the flatten
- `cache/chroma` binary files are NOT committed
- Overpass mirror kumi.systems consistently times out — listed last in the mirror list
