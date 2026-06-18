# RouteIQ — Session 24 Handoff

**Date:** 2026-06-16
**Branch:** `feature/routeiqagent`
**Tests:** 187 passing (all green — stepper + test patch written this session)
**Status:** Stepper code WRITTEN (uncommitted). Route-scheduling design PLANNED (not yet coded).

---

## What changed this session

### 1. In-app stepper for Day Trip agent (WRITTEN, not yet committed)

Replaced the static `"🤖 Agent is planning…"` info box with a live 3-step stepper matching Route Planner's visual style.

**Files changed (dirty, not committed):**

- **`routeiq/agent/day_trip_agent.py`**
  - Added module-level `_progress_registry: dict[str, dict]` + `threading.Lock()`
  - Added `register_progress(thread_id, d)` and `unregister_progress(thread_id)` (called by app.py)
  - Added `_TOOL_TO_STEP` dict: `find_city_pois/enrich/get_travel_time/estimate → "find_pois"`, `rate_pois → "rate_pois"`
  - Added `_emit_progress(thread_id, step, subtask)` — marks prev step done, sets current
  - `_plan(state, config: Optional[RunnableConfig])` — now accepts LangGraph config param, extracts `thread_id`, calls `_emit_progress` before each tool batch and before structured extraction (`"extract"` step)

- **`app.py`**
  - `_render_stepper(state, steps=None)` — now takes optional `steps` param (reuses same CSS/render for both tabs)
  - Added `_DT_STEPS = [("find_pois", "Discovering city POIs", "🏙️"), ("rate_pois", "Rating stops", "⭐"), ("extract", "Finalizing itinerary", "📋")]`
  - Planning-start block: `register_progress(new_thread_id, dt_progress)` before thread launch; stores in `session_state["dt_progress"]`
  - Planning poll: replaces static `st.info()` with `_render_stepper(dt_progress, steps=_DT_STEPS)`
  - Thread-done: `unregister_progress(thread_id)`
  - Refine path: also registers progress dict before refine thread

- **`tests/agent/test_day_trip_agent.py`**
  - Fixed 3 tests that were patching `routeiq.agent.day_trip_agent._make_llm` (old name, removed in Session 23) → now patch `routeiq.agent.day_trip_agent.create_llm`

**Commit these before starting Session 25 work:**
```bash
git add routeiq/agent/day_trip_agent.py app.py tests/agent/test_day_trip_agent.py
git commit -m "feat: Day Trip agent live stepper + fix test patch target"
```

---

### 2. Real route scheduling + visual polish — DESIGNED (plan ready, not coded)

Full plan at: `/Users/ayyaswamy/.claude/plans/i-don-t-understand-without-squishy-wave.md`

**Problem identified:** The Day Trip agent hallucinates arrival/departure times.
- `get_travel_time` tool: haversine / 30 km/h — no road network
- `estimate_visit_duration`: hardcoded table — ok for LLM reasoning but times not wired into schedule
- Extraction LLM fills `arrival_time`/`departure_time` with zero grounding
- Time budget never enforced — no stops trimmed

**Design decisions locked:**

| Decision | Rationale |
|---|---|
| `_schedule_stops()` runs **after** structured extraction | LLM picks which stops and rough order; deterministic Python does the real scheduling |
| Nearest-neighbor sort by `composite_score` before routing | `rate_pois` passes stops best-first; nearest-neighbor preserves best-first while keeping route geographically tight → tail = lowest priority stop → tail-trimming removes correct stop |
| 7-min transition overhead per leg | Parking + walking to POI entrance. Separate from `visit_duration_min` (time spent at POI). Consistent with existing `_OVERHEAD_MIN = 5.0` in `get_travel_time` tool but bumped for RouteGraph precision |
| Graceful fallback on graph/geocode failure | Returns original stops + empty `route_coords` — UI still works, just with LLM-estimated times |
| Indigo `#6366f1` for Day Trip AntPath | Distinguishes from Route Planner blue `#0066cc`; matches existing visitor-quote border accent |

---

## What to build next session (Session 25)

### Build order

#### Step 1 — Commit stepper code first (see git command above)

#### Step 2 — `routeiq/agent/agent_state.py`
Add one field to `DayTripState`:
```python
route_coords: Optional[List[tuple]]   # (lat, lon) pairs for AntPath; None until _schedule_stops runs
```

#### Step 3 — `routeiq/agent/day_trip_agent.py` — `_schedule_stops` + helpers

New imports:
```python
import re as _re
from routeiq.graph.graph_loader import GraphLoader
from routeiq.graph.route_graph import RouteGraph
```
`osmnx` imported lazily inside `_schedule_stops` body (project convention).

Two helpers above `_schedule_stops`:
- `_minutes_to_timestr(total: float) -> str` — minutes-since-midnight → `"10:30 AM"`
- `_timestr_to_minutes(s: str) -> float | None` — inverse, used for budget check

`_schedule_stops(stops, start_time, time_budget_hours, city) -> tuple[list[dict], list[tuple]]`:
1. Parse `start_time` ("9:00 AM") → float minutes since midnight
2. Lazy `import osmnx as ox; gdf = ox.geocoder.geocode_to_gdf(city)` → centroid lat/lon
3. `GraphLoader().load(lat±0.15, lon±0.15)` → graph G  ← pickle-cached, fast for SF
4. `rg = RouteGraph(G)`
5. **Nearest-neighbor sort**: start from stop with max `composite_score`; greedily pick nearest remaining stop by haversine. Fallback: preserve LLM order if `composite_score` absent.
6. For each consecutive pair: `rg.find_route()` → append coords to `leg_coord_slices[i]`; accumulate `drive_time_min + 7.0`
7. Per-stop: `arrival_time = prev_departure + drive_min`; `departure_time = arrival + visit_duration_min`
8. Budget trim loop: `while last_stop.departure > start + budget*60: pop() + discard coord slice`
9. Flatten kept slices: `all_coords = [c for s in leg_coord_slices[:len(kept)] for c in s]`
10. **Any exception → `return original_stops, []`** (graceful fallback, no crash)

Wire into `_plan()` after structured extraction:
```python
scheduled, route_coords = _schedule_stops(
    itinerary_dict.get("stops") or [],
    state["start_time"], state["time_budget_hours"], state["city"],
)
itinerary_dict["stops"] = scheduled
return {"messages": messages, "draft_itinerary": itinerary_dict, "route_coords": route_coords}
```

Also in this file — photo fix:
- `ItineraryStop.photo_urls` field: add `description="Copy photo_urls exactly from rate_pois tool results. Do not invent URLs."`
- Extraction prompt: add `"CRITICAL: copy photo_urls, rating, review_count, review_source, and hours EXACTLY from rate_pois tool output — do not invent or modify these values."`

#### Step 4 — `routeiq/ui/card_renderer.py` — `render_dt_card`

Add `render_dt_card(stop: dict, rank: int) -> str`:
- Reuses `_CARD_WRAP`, `_img_tag`, `_PLACEHOLDER`
- Photo: `photo_urls[0]` → fallback `image_url` → `_PLACEHOLDER`; zoom via `riShow()`
- Body rows (matching `render_stop_card` structure):
  - Category badge (`CATEGORY_COLORS`) + time slot `"9:00 AM – 10:30 AM"`
  - `rank. name` bold
  - `⭐ 4.6 (12,000) · TripAdvisor` amber/gray
  - `why_visit` 2-line clamp
  - `visitor_quote` with indigo left-border
  - Activity badges ≤3
  - `🕐 hours` footer

#### Step 5 — `routeiq/ui/__init__.py`
Add `render_dt_card` to import + `__all__`.

#### Step 6 — `app.py` — Four targeted changes

**6a.** Import `render_dt_card`.

**6b.** Add `"route_coords": None` to `initial_state` dict.

**6c.** Capture `route_coords` from snapshot (planning-complete handler) and from `_run_dt_narrate_thread` result dict. Clear on new plan start.

**6d.** Replace `if dt_phase == "done":` block:
```
[city · Xh · N stops header]
[map col 3/5 | cards col 2/5]   ← same layout as Route Planner
   map: CartoDB positron + AntPath(route_coords, #6366f1) + numbered DivIcon markers
   cards: render_dt_card per stop in 500px scrollable div + IMAGE_MODAL_HTML
[Trip narrative expander — below columns]
```

#### Step 7 — Tests

Patch `_schedule_stops` in existing test classes (it makes external calls):
```python
@pytest.fixture(autouse=True)
def _no_schedule(monkeypatch):
    monkeypatch.setattr(
        "routeiq.agent.day_trip_agent._schedule_stops",
        lambda stops, *_: (stops, []),
    )
```
Apply to `TestInterruptFires`, `TestResumeApproved`, `TestResumeRefine`.

New `TestScheduleStops` class:
- `test_empty_stops_returns_empty`
- `test_returns_original_on_geocode_failure`
- `test_returns_original_on_graph_load_failure`
- `test_first_stop_gets_start_time`
- `test_budget_drops_last_stop` — 3 stops, 4h budget too tight for 3rd → `len == 2`
- `test_minutes_to_timestr_*` (noon, midnight, 9 AM, 2:30 PM)

---

## Verification checklist (Session 25 end)

1. `python3 -m pytest tests/ -v` — 195+ tests pass
2. `bash restart.sh` → Tab 1 Day Trip Planner
3. Plan SF, 8h, 9 AM — stepper shows 3 steps live during planning
4. Draft cards approve → **"done" view**: AntPath polyline on CartoDB map + numbered indigo markers; TripAdvisor photo cards right column with real `"9:00 AM – 10:30 AM"` time slots grounded in OSMnx routes
5. Server log shows `[_schedule_stops] ...` timing prints
6. Plan with tight budget (4h, many interests) — verify stops trimmed with log `"dropping 'X'"` 
7. Photos visible in "done" cards (TripAdvisor photo_urls fix)
8. Non-SF city (e.g. Austin, TX) — graceful fallback: schedule shown, no polyline, no crash

---

## Key gotchas for Session 25

- `GraphLoader` uses pickle cache in `./cache/graphs/` — SF graph likely already cached from Route Planner preload; other cities download from Overpass on first run (~1-3 min)
- `RouteGraph` default speed is 50 km/h — urban city trips, appropriate
- `leg_coord_slices[0]` is empty list (no drive leg before first stop) — must handle in flatten
- `composite_score` field is already in each stop dict from `rate_pois` output — no extra API call needed for sort
- `_timestr_to_minutes` must handle both "9:00 AM" and "10:30 AM" formats robustly (1 or 2 digit hours)
- `import osmnx as ox` inside `_schedule_stops` body — NOT at module scope (startup perf)
- `route_coords` must be added to `initial_state` dict in app.py (LangGraph TypedDict validation)

---

## Git state

- Branch: `feature/routeiqagent`
- Last committed: `1120b0e` (feat: Day Trip Planner agent + ratings layer + UI)
- **Dirty files (stepper — ready to commit):**
  - `routeiq/agent/day_trip_agent.py`
  - `app.py`
  - `tests/agent/test_day_trip_agent.py`
- 187/187 tests passing on dirty tree
