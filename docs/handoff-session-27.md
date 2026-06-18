# Handoff — Session 27

**Date:** 2026-06-17
**Branch:** `feature/routeiqagent`
**Tests:** 198/198 passing
**Commits this session:** 0 (all changes are uncommitted dirty files)

---

## What was done this session

Four independent bugs investigated and fixed, plus a root cause diagnosis of broken rating APIs.

---

### Bug 1 — Artifact line near Muir Roads (RESOLVED)

**Hypothesis confirmed:** B — wrong graph centroid.

The log analysis showed:
```
schedule city='San Francisco, CA' polygon_centroid=(37.7598,-122.6941)
schedule graph loaded — 246 nodes
schedule leg 0→1 'Coit Tower'→'Palace of Fine Arts': OK 1 coords first=(37.883062, -122.5447966) last=(37.883062, -122.5447966)
```

`geocode_to_gdf("San Francisco, CA").geometry.iloc[0].centroid` returned `(37.7598, -122.6941)` — the polygon centroid dragged ~25 km into the Pacific Ocean by the **Farallon Islands** (part of SF City/County). This was an exact cache hit for `n37.910_s37.610_e-122.544_w-122.844.pkl` — a 246-node graph covering ocean west of Twin Peaks. All 8 stops sit at lon −122.40 to −122.49, east of the graph's −122.544 eastern boundary. `nearest_nodes` snapped every stop to the same two boundary nodes at the GG Bridge / Marin edge, creating the artifact.

**Fix — `routeiq/agent/day_trip_agent.py`:**

Replaced `geocode_to_gdf(...).geometry.iloc[0].centroid` with `ox.geocode(city)`. Nominatim's point lookup returns `(37.7879, −122.4075)` for SF — downtown, not skewed by the Farallons. Works for any city without special-casing.

```python
# Before
gdf = ox.geocoder.geocode_to_gdf(city)
centroid = gdf.geometry.iloc[0].centroid
lat, lon = centroid.y, centroid.x

# After
lat, lon = ox.geocode(city)
```

**Side effect:** First SF plan after the fix will trigger a fresh Overpass download for the correctly-centred bbox (`n37.938_s37.638_e-122.257_w-122.557` or similar); subsequent runs hit the new cache. No existing cache covers the correct bbox.

**Tests updated — `tests/agent/test_day_trip_agent.py`:**
- All 4 `_schedule_stops` tests patched `osmnx.geocoder.geocode_to_gdf` → `osmnx.geocode`
- `_mock_osmnx_gdf` (complex GDF mock) replaced with `_mock_geocode` → returns `(37.77, -122.41)` tuple

---

### Bug 2 — Golden Gate Bridge absent from SF itinerary (RESOLVED)

**Root cause:** `get_pois_for_city("San Francisco")` was filtering out GGB before the polygon check could run.

The KG's `_nearest_city` heuristic assigned GGB's `LOCATED_IN` edge → **Sausalito** (Sausalito's centroid is 2 km closer to the bridge midpoint than SF's centroid). The old code pre-filtered with:
```python
if poi_city is not None and poi_city != short:
    continue   # GGB blocked here — never reaches polygon check
```
The polygon check (added in Session 26) would correctly include GGB — `(37.8203, −122.4786)` is inside SF's admin boundary — but GGB never reached it.

**Fix — `routeiq/graph/knowledge_graph.py` `get_pois_for_city`:**
- When polygon is available: polygon is the sole spatial gate (pre-filter removed)
- When polygon is None (fetch failed): fall back to LOCATED_IN heuristic (original behavior, handles unknown cities like "Atlantis")

```python
if city_poly is not None:
    if not city_poly.contains(Point(poi.lon, poi.lat)):
        continue
else:
    # No polygon — fall back to LOCATED_IN heuristic
    poi_city = self._city_for_poi(node_id)
    if poi_city is not None and poi_city != short:
        continue
```

**Test updated — `tests/test_knowledge_graph.py`:**
- `test_get_pois_for_city_sf_returns_pois` now asserts `"Golden Gate Bridge" in names`

---

### Bug 3 — Wikipedia signal useless in composite score (RESOLVED)

All 58 SF POIs have a `wikipedia_tag` — the `has_wikipedia` boolean gave a flat +0.03 to every single POI, providing zero differentiation. Score effectively reduced to `0.4 × rating + 0.3 × log(reviews)`.

**Fix — `routeiq/agent/tools/rate_pois.py`:**

Replaced `has_wikipedia: bool` with `wikipedia_tag: str | None`:

```python
def _wikipedia_weight(wikipedia_tag: str | None) -> float:
    if not wikipedia_tag:
        return 0.0
    return 0.1 if wikipedia_tag.startswith("en:") else 0.01
```

- `en:` Wikipedia articles → +0.03 (real English Wikipedia, correlates with significance)
- `ceb:` / other language tags → +0.003 (auto-generated stubs like `ceb:Aquatic Cove`)
- No tag → 0

Both `_composite_score` call sites updated to pass `rp.poi.wikipedia_tag` (the full tag string) instead of `bool(rp.poi.wikipedia_tag)`.

---

### Bug 4 — `visitor_summary` and extra photos not rendered (RESOLVED)

The LLM generates `visitor_summary` (1–2 sentence synthesis of all reviewer sentiment) and the agent fetches up to 5 TripAdvisor photos. Neither was being displayed.

**Fix — `routeiq/ui/card_renderer.py` `render_dt_card`:**

1. **`visitor_summary`** — added as a 💬 gray pill block below `visitor_quote`:
   ```html
   <div style="font-size:11px;...background:#f8fafc;border-radius:5px;padding:5px 8px;">
     <span>💬</span>{visitor_summary}
   </div>
   ```

2. **Extra photos** (`photo_urls[1–3]`) — added as a clickable thumbnail strip below the main card row. Each thumbnail opens the existing `riShow()` lightbox on click.

3. Card structure changed from `_CARD_WRAP.format(...)` (single flex row) to a custom wrapper that supports `[flex row] + [photo strip]`.

Card field order: rating → why_visit (Wikipedia) → visitor_quote (vivid snippet) → visitor_summary (LLM synthesis) → activity badges → hours → photo strip.

---

### Root cause diagnosis — TripAdvisor/Foursquare APIs both broken

Tested both APIs directly:
- **TripAdvisor** → **403 Forbidden** (key expired or unauthorized)
- **Foursquare** → **401 Unauthorized** (invalid token)

The stale empty TripAdvisor pool cache (`cache/ratings/tripadvisor_san_francisco_ca_pool.json` = `[]`) was being served from June 16 and had a 21-day TTL — every run silently got no ratings, no reviews, no photos.

**Immediate fix:**
- Deleted the stale cache file so the next run retries the live API

**Structural fix — `routeiq/agent/day_trip_agent.py` `_backfill_images()`:**

Added automatic Wikipedia thumbnail backfill after `_schedule_stops`. For every stop with no `photo_urls` and no `image_url`, fetches a Wikipedia thumbnail via `WikipediaFetcher().enrich()` in a `ThreadPoolExecutor(max_workers=6)`. ~0.5 s for 8 stops.

```python
def _backfill_images(stops: list[dict]) -> None:
    needs_image = [s for s in stops if not (s.get("photo_urls") or s.get("image_url"))]
    def _fetch_one(stop):
        poi = POI(name=stop["name"], ...)
        WikipediaFetcher().enrich(poi)
        if poi.image_url:
            stop["image_url"] = poi.image_url
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_fetch_one, needs_image))
```

Called in `_plan()` right after `_schedule_stops`, with progress label "Fetching images…".

**Action required — new API keys:**
```
# In .env — keep only ONE RATING_PROVIDER line:
RATING_PROVIDER=tripadvisor
TRIPADVISOR_API_KEY=<new key from developers.tripadvisor.com>
# OR:
RATING_PROVIDER=foursquare
FOURSQUARE_API_KEY=<new key from developer.foursquare.com>
```
- TripAdvisor Content API: free tier 5k calls/month
- Foursquare Places API: free tier 1k calls/day

Until keys are refreshed, all stops get Wikipedia images (confirmed working). Ratings, review snippets, `visitor_quote`, `visitor_summary` will be empty.

---

## Key files changed this session

| File | Change |
|---|---|
| `routeiq/agent/day_trip_agent.py` | `ox.geocode()` for schedule centroid; `_backfill_images()` helper; progress label "Fetching images…" |
| `routeiq/graph/knowledge_graph.py` | `get_pois_for_city` — polygon gate only when available; LOCATED_IN fallback when polygon is None |
| `routeiq/agent/tools/rate_pois.py` | `_wikipedia_weight(tag)` differentiates `en:` vs `ceb:`; both call sites updated |
| `routeiq/ui/card_renderer.py` | `render_dt_card` — `visitor_summary` pill; extra photo thumbnail strip |
| `tests/agent/test_day_trip_agent.py` | `osmnx.geocode` patch; `_mock_geocode` replaces `_mock_osmnx_gdf` |
| `tests/test_knowledge_graph.py` | Assert GGB IS in SF POI list |
| `cache/ratings/tripadvisor_san_francisco_ca_pool.json` | Deleted (stale empty cache) |

---

## Current state

| Feature | Status |
|---|---|
| Artifact line bug | ✅ Fixed |
| Golden Gate Bridge in SF results | ✅ Fixed |
| Route lines stop-to-stop | ✅ Fixed (Session 26 centroid fix + Session 27 graph bbox fix) |
| Wikipedia images for all stops | ✅ Working (backfill always runs) |
| TripAdvisor ratings / reviews / photos | ❌ API key 403 — needs new key |
| Foursquare ratings | ❌ API key 401 — needs new key |
| visitor_summary rendered in card | ✅ Wired — will show once API returns data |
| Extra photo thumbnails in card | ✅ Wired — will show once API returns photos |

---

## Next session priorities

### 1 — Refresh API keys (10 min)
Get a working TripAdvisor or Foursquare key, set a single `RATING_PROVIDER=` in `.env`, restart app, run SF plan, confirm ratings/reviews/photos appear in cards.

### 2 — Google Doc (Week 3 submission)
Merge `docs/agent-architecture.md` + `docs/scope-definition.md` into a coherent Week 3 submission doc covering:
- Agent architecture (LangGraph ReAct loop → interrupt → narrate)
- Tools used and why (find_city_pois, rate_pois, enrich_poi_details, estimate_visit_duration)
- Knowledge graph design decisions
- Evaluation / what the agent does well vs. where it falls short

### 3 — Demo recording
Live stepper → draft map with route lines → approve → done view with narrative.
Confirm GGB appears in SF results and images show for all stops.

---

## Env vars required

```
LLM_PROVIDER=nebius
NEBIUS_API_KEY=...
LLM_MODEL=...
NEBIUS_API_BASE=...
TRIPADVISOR_API_KEY=<needs refresh>    # OR use foursquare
FOURSQUARE_API_KEY=<needs refresh>
RATING_PROVIDER=tripadvisor            # only ONE line
LANGCHAIN_TRACING_V2=true             # optional — LangSmith
LANGCHAIN_API_KEY=...                  # optional
LANGCHAIN_PROJECT=routeiq             # optional
```
