# Session 10 Handoff — Performance Overhaul

**Date:** 2026-06-10  
**Branch:** feat/days-1-3-graph-rag-pipeline  
**Status:** All perf fixes committed, 124/124 tests passing

---

## What we fixed this session

Three runtime bottlenecks were profiled and fixed, plus one startup bottleneck discovered mid-session.

### 1. Graph cache: graphml → pickle (~5× faster reads)

**Problem:** `ox.load_graphml()` parses XML on every load. For a cached graph that should be instant, this took **3.45s**.

**Fix:** `routeiq/graph/graph_loader.py`
- Saves new downloads as `{key}.pkl` (Python pickle, binary) instead of `{key}.graphml`
- Auto-migrates existing `.graphml` on first access: loads with OSMnx, saves `.pkl`, uses `.pkl` from then on
- `_find_containing_cache()` updated to match both `.pkl` and `.graphml`; prefers `.pkl`
- No external API changes — callers unchanged

**Result:** Cache reads drop from ~3.5s to ~0.7s.

**Gotcha:** `cache/graphs/` now contains `.pkl` files alongside any legacy `.graphml`. Both are valid — the migration is automatic.

---

### 2. Wikipedia enrichment: serial → parallel (~4× faster)

**Problem:** 5 POIs × ~0.37s each = **1.84s** in serial.

**Fix:** `routeiq/pipeline.py` `_rag_node`
```python
with ThreadPoolExecutor(max_workers=min(5, len(top_pois))) as pool:
    list(pool.map(lambda sp: WikipediaFetcher().enrich(sp.poi), top_pois))
```
- Each thread creates a fresh `WikipediaFetcher()` (own `requests.Session`) — avoids shared-state thread-safety issues on `Session`
- All 5 Wikipedia fetches fire simultaneously

**Result:** 1.84s → **~0.44s** (confirmed in logs).

---

### 3. Claude narrate: blocking → streaming

**Problem:** 11.39s wait with blank screen before narrative appears.

**Fix (three files):**

`routeiq/insights/narrative_chain.py` — added `stream()` method:
```python
def stream(self, origin, destination, ...) -> Iterator[str]:
    yield from self._chain.stream({...})
```

`routeiq/pipeline.py` `_narrate_node` — consumes stream, fires `narrate_stream` progress events:
```python
for chunk in self._narrative_chain.stream(...):
    narrative += chunk
    self._progress("narrate_stream", chunk)
```

`app.py` `_on_progress` — renders streamed text live into a placeholder:
```python
if step == "narrate_stream":
    _narrative_buffer[0] += subtask
    narrative_stream_placeholder.markdown(...)
    return
```

**Result:** User sees narrative text appearing token-by-token during the 11s Claude call instead of a blank wait. The `narrative_stream_placeholder` is cleared after `facade.run()` returns; final result renders normally in the expander.

---

### 4. Startup: 30s blank screen → ~2s

**Problem:** `_T0 = time.perf_counter()` was set on line 20, *after* module-level imports:
```python
from routeiq.graph import GraphLoader   # → osmnx + pandas + shapely: ~25s
from routeiq.ui import MapBuilder       # → folium: ~2s
import osmnx as ox                      # already cached, 0s
```
The timer started after all the heavy work finished, so logs showed "0.03s" and the 25-30s was invisible.

**Fix:** `app.py`
- `_T0` moved to be the very first line (after stdlib only)
- Import logging added: `_log("import: streamlit")`, `_log("import: streamlit_folium")`, etc.
- All heavy imports (`osmnx`, `routeiq.graph`, `routeiq.ui`) moved inside `_load_lightweight()`
- Module-level `_load_lightweight()` call replaced with a daemon background thread:
  ```python
  _bg_init_thread = threading.Thread(target=lambda: _load_lightweight(), daemon=True)
  _bg_init_thread.start()
  ```
- `@st.cache_resource` is thread-safe — background thread populates the cache; Streamlit calls return the cached result instantly

**Result:** Page renders in **~2–4s** (just `streamlit` + `streamlit_folium` imports). Heavy init runs in background. Banner shows "Loading RouteIQ components…" while `_bg_init_thread.is_alive()`.

**Gotcha:** Results section gets `map_builder` lazily — `_, _map_builder, _ = _load_lightweight()` — since it's cached, this is instant by the time a query result renders.

---

### 5. Overpass mirror failover: 215s → ~30s

**Problem:** kumi.systems (first mirror) was timing out, but OSMnx **retries 5× internally** before raising:  
`5 attempts × 45s timeout = 225s ≈ 215s` observed.  
Our mirror loop never got control back until all retries exhausted.

**Fix (two layers):**

`app.py` `_load_lightweight()` — kill OSMnx retry amplification:
```python
ox.settings.requests_max_retries = 0       # 1 attempt per mirror, no retries
ox.settings.requests_timeout = 30          # 30s HTTP socket timeout (was 45s)
ox.settings.overpass_settings = "[out:json][timeout:28]"  # server gives up at 28s
```

`routeiq/graph/poi_finder.py` — hard wall-clock timeout per mirror via daemon thread:
```python
fetch_thread = threading.Thread(target=_fetch, daemon=True)
fetch_thread.start()
fetch_thread.join(timeout=_PER_MIRROR_TIMEOUT)  # 30s hard limit

if fetch_thread.is_alive():
    print(f"TIMEOUT after {elapsed:.1f}s → next mirror")
    continue
```
This enforces 30s regardless of OSMnx's internal behavior — the thread keeps running but we move on.

**Mirror order reordered** (`graph_loader.py` + `app.py`):
```
lz4.overpass-api.de   ← reliable, now first
z.overpass-api.de
overpass.openstreetmap.ru
overpass.kumi.systems  ← consistently timing out, now last
```

**Result:** kumi.systems failure costs **30s** (was 215s). If lz4 is up (it usually is), total failover cost is 30s + ~11s = **41s** on first query for a new corridor. Subsequent queries hit the POI JSON cache (`cache/pois/*.json`).

---

## Timing summary (SF → Monterey, cold cache)

| Stage | Before | After |
|---|---|---|
| Startup (to page render) | ~30s blank | ~2–4s |
| Graph cache load | 3.45s | ~0.7s |
| Overpass mirror failover | 215s | ~30s |
| Wikipedia (5 POIs) | 1.84s | ~0.44s |
| Narrate (UX) | 11s blank wait | tokens stream live |

---

## POI volume note (12,656 rows → 521 → 5)

For SF→Monterey, `features_from_bbox()` returns 12,656 raw OSM features because the **bounding box** of the 5km buffer polygon covers ~14,000 km² (a large rectangular area). The Python-side `buffer_poly.contains(centroid)` filter cuts this to 521 POIs that actually lie within the 5km corridor. The scoring + selection step then picks the best 5.

This is expected and working as designed. The filtered 521 are cached to `cache/pois/*.json` — subsequent queries for the same corridor show `poi cache HIT` in ~0.1s.

---

## Files changed this session

| File | Change |
|---|---|
| `app.py` | Deferred heavy imports, background init thread, streaming narrate UI, Overpass settings |
| `routeiq/graph/graph_loader.py` | Pickle cache, graphml migration, mirror order |
| `routeiq/graph/poi_finder.py` | Hard 30s timeout per mirror via daemon thread |
| `routeiq/insights/narrative_chain.py` | `stream()` method added |
| `routeiq/pipeline.py` | Parallel Wikipedia, streaming narrate node |
| `tests/test_graph_loader.py` | Updated for pickle; added migration test |
| `tests/test_narrative_chain.py` | Added `TestNarrativeChainStream` |
| `tests/test_pipeline.py` | `narrate_node` now asserts `stream()` not `generate()` |

---

## What's still next (Day 5 remaining)

- [ ] README.md with architecture diagram + Quick Start + tech stack
- [ ] Test all 4 demo queries end-to-end, confirm stop cards + streaming narrative appear
- [ ] Record demo video (≤ 5 min): live walkthrough + GraphRAG vs vector comparison
- [ ] Google Doc: pull from `docs/learnings.md` for iterations/learnings sections
- [ ] Submit: GitHub + Google Doc + recording
