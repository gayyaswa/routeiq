# RouteIQ — Session 9 Handoff

**Date:** 2026-06-10
**Branch:** feat/days-1-3-graph-rag-pipeline (ahead of remote, NOT pushed)
**Tests:** 121/121 passing
**Last commit:** `8a4b3fd` — perf: Overpass resilience, POI/graph caching, lazy startup, timing instrumentation

---

## Top priority for next session: 3 performance fixes

Timing instrumentation was added this session. Here are the measured bottlenecks and approved fixes.

### Fix 1 — Graph load: graphml → pickle (3.45s → ~0.5s)

`ox.load_graphml()` parses XML — slow for 50–200MB files.
NetworkX pickle loads the same graph ~5-10x faster.

**Files to change:** `routeiq/graph/graph_loader.py`

```python
# Save: replace ox.save_graphml with nx.write_gpickle
import pickle
with open(path, "wb") as f:
    pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

# Load: replace ox.load_graphml with pickle.load
with open(path, "rb") as f:
    G = pickle.load(f)
```

- Change cache file extension from `.graphml` to `.pkl`
- Update `_BBOX_RE` in `_find_containing_cache` to match `.pkl`
- Existing `.graphml` files in `cache/graphs/` still work as fallback
  (check for `.pkl` first, then `.graphml`, then download)
- Key format stays the same: `n{north:.3f}_s{south:.3f}_e{east:.3f}_w{west:.3f}.pkl`

**Note:** `cache/graphs/` has 9 existing `.graphml` files (55–211MB each).
On first run after the change, each will be re-downloaded as `.pkl`.
OR: write a one-off migration script to convert existing files.

---

### Fix 2 — Wikipedia enrichment: serial → parallel (1.84s → ~0.4s)

Currently sequential: each POI's Wikipedia fetch blocks the next.

**File to change:** `routeiq/pipeline.py` `_rag_node`

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

if self._wikipedia_fetcher is not None:
    self._progress("rag", "Enriching POIs with Wikipedia…")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(self._wikipedia_fetcher.enrich, sp.poi): sp for sp in top_pois}
        for future in as_completed(futures):
            sp = futures[future]
            self._progress("rag", f"Fetched {sp.poi.name}…")
```

`WikipediaFetcher.enrich()` is already safe to call concurrently — it only writes
to the POI object it receives, no shared state.

---

### Fix 3 — Narrative: stream Claude response (11.39s wall → text appears immediately)

Instead of waiting 11s for the full narrative, stream tokens to the UI as they arrive.

**Files to change:** `routeiq/insights/narrative_chain.py` + `app.py`

In `NarrativeChain`, add a `stream()` method alongside the existing `generate()`:
```python
def stream(self, **kwargs):
    """Yields text chunks as Claude generates them."""
    chain = self._prompt | self._llm
    for chunk in chain.stream(self._build_inputs(**kwargs)):
        yield chunk.content
```

In `app.py`, replace the narrate section with a streaming placeholder:
```python
narrative_placeholder = st.empty()
full_narrative = ""
for chunk in facade.stream_narrative(...):
    full_narrative += chunk
    narrative_placeholder.markdown(full_narrative + "▌")
narrative_placeholder.markdown(full_narrative)
```

This requires the pipeline to support a streaming path — either:
- Add `stream_narrative()` to `RouteIQFacade` (simplest, bypasses LangGraph)
- Or pipe LangGraph's streaming events through to the UI

**Recommended:** add `facade.stream_narrative()` as a separate method that
streams the narrative chain directly, called after `facade.run()` returns
(which already has the POI context). Replace the stored narrative in state.

---

## Current timing baseline (SF → Monterey, all caches warm)

```
_load_heavy (startup):    0.67s  ← already fast
parse node (Claude):      1.82s
  geocode:                0.00s
  graph load (XML):       3.45s  ← Fix 1
  A* pathfind:            0.30s
  poi cache HIT:          0.00s
  score+select:           0.07s
graph node total:         3.82s
  wikipedia x5 serial:    1.84s  ← Fix 2
rag node total:           1.85s
narrate node (Claude):   11.39s  ← Fix 3
TOTAL:                  ~19s
```

Target after all 3 fixes: **~8–10s** total.

---

## What was done this session (Session 9)

- Overpass mirror fallback in both `GraphLoader` and `POIFinder`
- `overpass_rate_limit = False` — skips the slow `/status` pre-check
- Fuzzy bbox containment in `GraphLoader` — cached graph reused when it covers the corridor
- POI disk cache (`cache/pois/*.json`) — repeat queries skip Overpass entirely
- `winery` added to scenic tourism OSM tags
- `top_n` back to 5
- Single shared ChromaDB client — one SQLite open instead of three
- Vector baseline seeded only when collection is empty (skips embedding on warm restart)
- Lazy startup — `osmnx`, `chromadb`, `langchain` deferred to first button click
- Vector narrative generated lazily (only when user opens Vector Baseline expander)
  — eliminates ~11s post-pipeline pause before map renders
- Timing instrumentation: `[timing]` prints in `pipeline.py` and `poi_finder.py`
- `time_startup.py` standalone script for import/init profiling

---

## Key files

| File | What it does |
|---|---|
| `app.py` | Streamlit — lazy `_load_lightweight` / `_load_heavy`, timing logs |
| `routeiq/pipeline.py` | LangGraph nodes — timing on every step |
| `routeiq/graph/graph_loader.py` | graphml cache + mirror fallback + bbox containment |
| `routeiq/graph/poi_finder.py` | POI disk cache + mirror fallback + timing |
| `routeiq/facade.py` | Shared ChromaDB client wired through |
| `time_startup.py` | Standalone import/init timing script |
| `cache/graphs/*.graphml` | 9 cached road network graphs — do NOT delete |
| `cache/pois/*.json` | Cached POI scan results — safe to delete to re-fetch |

## How to run

```bash
./restart.sh
python3 -m pytest tests/ -v   # 121 tests
python3 time_startup.py        # import + init timing (no API key needed for imports)
```

## Gotchas

- Branch is ahead of remote — do NOT push until explicitly asked
- `cache/graphs/` must NOT be deleted — 2–5 min to rebuild per corridor
- Timing prints go to terminal (stdout), not the browser
- `time_startup.py` skips LLM/pipeline steps if `ANTHROPIC_API_KEY` is not set
- After Fix 1 (pickle), existing `.graphml` files need migration or re-download
