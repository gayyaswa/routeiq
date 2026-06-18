# Handoff — Session 26

**Date:** 2026-06-17
**Branch:** `feature/routeiqagent`
**Tests:** 198/198 passing
**Commits this session:** 0 (all changes are uncommitted dirty files)

---

## What was done this session

All changes stem from one persistent bug: an artifact line appearing near Muir Roads on the
Day Trip Planner draft map for San Francisco, with no route lines connecting the actual 5 stops.

### Investigation trail

Multiple root causes were found and fixed in layers:

#### 1 — `get_pois_for_city` used `_nearest_city` heuristic (root cause)

`knowledge_graph_data.py` assigns each Bay Area POI to a city using `_nearest_city()` — pure
haversine from POI to each city centroid, closest wins. Because SF's centroid is at the
northeast corner of the peninsula, some Marin County POIs (e.g. Muir Beach Overlook,
Marin Headlands) were closer to SF's centroid than to Sausalito's, so they got labeled
`LOCATED_IN → "San Francisco"` and were returned by `find_city_pois`.

**Fix applied — `routeiq/graph/knowledge_graph.py`:**
`get_pois_for_city` now fetches the real OSM administrative boundary polygon via
`ox.geocoder.geocode_to_gdf(city_name)` (cached per KG instance as `_poly_cache`) and
applies `Polygon.contains(Point(poi.lon, poi.lat))` as the authoritative spatial gate.
The `LOCATED_IN` edges remain as a coarse pre-filter; the polygon is the final word.
New helper: `_city_polygon(city_name)` — fetches + caches polygon, falls back to no filter
on network failure.

Also: `_expand_kg_for_city` in `app.py` (for dynamically added non-Bay-Area cities) was
given the same polygon clip after `find_pois_in_bbox`. This is belt-and-suspenders — SF is
pre-loaded so this path never runs for SF.

#### 2 — `get_travel_time` tool gave LLM false road-time data

`get_travel_time` used haversine (crow-flies) distance at a fixed 30 km/h. The LLM used it
to try to fit stops within the time budget — but SF road distances can be 2× straight-line
due to hills and one-way streets. The LLM was doing fake math, and `_schedule_stops` then
re-computed real A* times and trimmed stops anyway.

**Fix applied — `routeiq/agent/tools/__init__.py`:**
`get_travel_time` removed from `ALL_TOOLS`. LLM no longer has access to it.

**Fix applied — `routeiq/insights/prompts/day_trip_planner.py`:**
- Step 4 changed from "estimate_visit + get_travel_time — build the time schedule" to
  "estimate_visit_duration — get visit duration per stop subtype"
- Added explicit instruction: "Do NOT try to calculate travel times or fit stops within
  the time budget yourself — road-based scheduling is handled automatically"
- `arrival_time` / `departure_time` in the JSON template changed from example values
  (`"9:00 AM"`) to `"TBD"` — prevents LLM from anchoring on fake times
- LLM's job is now: select best 8–10 stops by quality + preferences. `_schedule_stops` owns
  all time math.

#### 3 — Observability infrastructure

**`routeiq/agent/day_trip_agent.py`:**
- `import logging` + `logger = logging.getLogger(__name__)`
- All existing `print(f"[dt_agent] ...")` calls in `_schedule_stops` replaced with
  `logger.debug` / `logger.warning`
- New `logger.debug` lines added for: polygon centroid, graph bbox, each input stop
  (name/lat/lon), each routing leg (success: first+last coord + coord count; failure: exc)

**`app.py`:**
- `logging.basicConfig(level=logging.DEBUG, ...)` wired after `load_dotenv()` — all
  `routeiq.*` DEBUG output now goes to the Streamlit terminal with timestamps

**LangSmith** (not yet wired — just documented):
Zero-code LangGraph auto-instrumentation. Add to `.env`:
```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<key from smith.langchain.com>
LANGCHAIN_PROJECT=routeiq
```
Every `graph.stream()` call auto-traces: tool inputs/outputs, LLM prompts/responses,
structured extraction, token counts, latency. Needed to see exactly which POIs the LLM
receives and selects.

---

## Unsolved — artifact line still present

Despite the polygon fix, the Muir-area artifact persists. Three hypotheses remain open:

### Hypothesis A — `geocode_to_gdf` silently failing in `_city_polygon`
If Nominatim rate-limits or times out, `city_poly = None` and the polygon filter is
bypassed entirely — Marin POIs pass through unchanged. The fix has a silent `except`
that stores `None`.

### Hypothesis B — `_schedule_stops` graph centroid is wrong
`_schedule_stops` calls `ox.geocoder.geocode_to_gdf(city)` to get the graph bbox centroid.
The SF administrative polygon includes bay tidal areas — its geometric `.centroid` is
shifted northeast (toward the bay / Marin direction). This shifts the graph bbox north,
potentially loading a cached graph that extends deep into Marin (`n38.590_...pkl` is
cached and goes to lat 38.59). `_find_containing_cache` with EPS=0.02 may select this
large Marin-inclusive graph for SF routing.

### Hypothesis C — Fort Point / Presidio `nearest_nodes` snap
Fort Point (lat 37.8106) is within SF's admin boundary and a legitimate stop. It sits
at the south foot of the GG Bridge. `nearest_nodes` might snap its coordinates to a road
node on the bridge approach in Marin, causing A* to briefly route through Marin before
returning to SF.

---

## Log analysis strategy (next session priority)

`basicConfig(level=DEBUG)` floods stdout with all library noise. The strategy for
efficient log analysis:

1. **Write routeiq-only logs to a file** — see `Log file setup` section below
2. **Next session: `grep` the file** for `[schedule]` prefix lines only
3. Analyze: centroid coords, graph bbox, stop coords, leg first/last coords

Specific grep patterns to run after the next SF plan attempt:
```bash
grep "schedule" logs/routeiq.log          # centroid, bbox, stops, legs
grep "leg.*FAILED" logs/routeiq.log       # which legs couldn't be routed
grep "first=" logs/routeiq.log            # first coord of each routed leg — check for Marin lat > 37.85
grep "kg.*polygon" logs/routeiq.log       # whether polygon fetch succeeded or fell back
```

---

## Key files changed this session

| File | Change |
|---|---|
| `routeiq/graph/knowledge_graph.py` | `get_pois_for_city` — OSM polygon gate + `_city_polygon` helper |
| `app.py` | `_expand_kg_for_city` polygon clip; `logging.basicConfig`; log-to-file handler (see below) |
| `routeiq/agent/tools/__init__.py` | `get_travel_time` removed from `ALL_TOOLS` |
| `routeiq/insights/prompts/day_trip_planner.py` | LLM selects stops; `_schedule_stops` owns time math; TBD times |
| `routeiq/agent/day_trip_agent.py` | `logging` module; structured DEBUG for centroid/bbox/stops/legs |

---

## Next session priorities

### 1 — Wire log file + run SF plan + analyze output (unblock artifact bug)

Apply the log-to-file config below, restart app, run SF plan, then:
```bash
grep "schedule" logs/routeiq.log
```
Share the output — 20–30 lines will definitively identify whether the issue is hypothesis
A (polygon bypass), B (wrong graph bbox), or C (nearest_nodes snap).

### 2 — Fix based on log findings

Expected fix depending on hypothesis:
- **A**: add an explicit `logger.warning` when polygon is None + test `geocode_to_gdf` in isolation
- **B**: use `CITIES` dict centroid for graph bbox instead of `geocode_to_gdf` polygon centroid (the CITIES dict already has `{"name": "San Francisco", "lat": 37.7749, "lon": -122.4194}` — use that as the stable anchor)
- **C**: add a `nearest_nodes` distance check in `find_route` — if snapped node is >500m from input coords, raise exception so the leg falls back gracefully

### 3 — Google Doc + demo recording

---

## Env vars required

```
LLM_PROVIDER=nebius
NEBIUS_API_KEY=...
LLM_MODEL=...
NEBIUS_API_BASE=...
TRIPADVISOR_API_KEY=...
FOURSQUARE_API_KEY=...       # optional
RATING_PROVIDER=tripadvisor
LANGCHAIN_TRACING_V2=true    # optional — LangSmith agent tracing
LANGCHAIN_API_KEY=...        # optional
LANGCHAIN_PROJECT=routeiq    # optional
```

---

## Log file setup (apply before next session run)

Replace the `logging.basicConfig` block in `app.py` with a two-handler config:
terminal gets WARNING and above (no noise); a rotating file gets DEBUG from routeiq only.

```python
import logging
from logging.handlers import RotatingFileHandler
import os

os.makedirs("logs", exist_ok=True)

# Terminal: WARNING+ only — keeps Streamlit output clean
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

# File: DEBUG for routeiq namespace only — readable by grep/Claude
_fh = RotatingFileHandler("logs/routeiq.log", maxBytes=5_000_000, backupCount=2)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s", datefmt="%H:%M:%S"))
logging.getLogger("routeiq").addHandler(_fh)
logging.getLogger("routeiq").setLevel(logging.DEBUG)
```

After running the SF plan, the file `logs/routeiq.log` will have only routeiq module output.
Share it or point Claude to it with Read — the scheduling debug lines will be ≤50 lines.
