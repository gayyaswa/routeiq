# Day 5 Handoff — Session 8

**Date:** 2026-06-10
**Branch:** feat/days-1-3-graph-rag-pipeline (1 commit ahead of remote, NOT pushed)
**Tests:** 121/121 passing

---

## Top priority for next session: Overpass API resilience

The app is crashing with `ReadTimeout` / `ConnectionError` against Overpass API servers.
A plan was written and approved — **implement this first**.

### Root causes (diagnosed)
1. OSMnx 2.x uses `overpass_url` not `overpass_endpoint` — the old setting silently did nothing
2. OSMnx does a `/status` pre-check (to determine rate-limit pause) which times out at 180s
3. No multi-mirror fallback — when one server is down, the whole app fails
4. `graph_loader.load()` is NOT inside a try/except in `_graph_node` — a network error
   crashes the pipeline uncaught instead of flowing to the fallback narrative

### Approved plan — 3 files to change

**`app.py`** (already has `overpass_url` set, just add these two lines):
```python
ox.settings.overpass_url = "https://overpass.kumi.systems/api"
ox.settings.overpass_rate_limit = False   # skip the /status pre-check
ox.settings.requests_timeout = 45         # fail fast (was 180)
```

**`routeiq/graph/graph_loader.py`** — replace the single `ox.graph_from_bbox()` call with a
mirror-fallback loop:
```python
_OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api",
    "https://lz4.overpass-api.de/api",
    "https://z.overpass-api.de/api",
    "https://overpass.openstreetmap.ru/api",
]
# In load(): cache check first (no network), then loop mirrors, save on first success
```

**`routeiq/pipeline.py`** — wrap `graph_loader.load()` in try/except in `_graph_node`:
```python
try:
    G = self._graph_loader.load(...)
except Exception as e:
    return {"error": "network_error", "fallback_reason": f"...", ...}
```

---

## Current app state

Everything from Session 7 is working when Overpass API is reachable:
- Animated vertical stepper (blinking icon, live sub-task messages) ✅
- Background graph preload + startup banner ✅
- POI data quality fixes (historic subtype allowlist, Wikipedia "California" suffix, 15s timeout) ✅
- Vector baseline isolated in own ChromaDB collection (routeiq_vector_baseline) ✅
- Dual narrative — GraphRAG and Vector Baseline each have own Claude narrative ✅
- docs/learnings.md written ✅

## Day 5 remaining work (after Overpass fix)

- [ ] **README.md** — Quick Start, architecture diagram, GraphRAG vs vector table
- [ ] **Test 4 demo queries** end-to-end, confirm stop cards (not fallback):
  1. `Drive from San Francisco to Monterey, show coastal history and natural landmarks`
  2. `Road trip from San Francisco to Napa Valley, show wineries and historic towns`
  3. `Drive from San Jose to Santa Cruz, show redwoods and beaches`
  4. `Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches`
- [ ] **Record demo** (≤ 5 min): live walkthrough + explain GraphRAG vs vector
- [ ] **Google Doc**: pull from docs/learnings.md
- [ ] **Submit**: GitHub + Google Doc + recording

## Key files

| File | What it does |
|---|---|
| `app.py` | Streamlit entry — stepper, preload thread, dual narrative |
| `routeiq/pipeline.py` | LangGraph nodes — parse→graph→rag→narrate, on_progress callback |
| `routeiq/graph/graph_loader.py` | OSMnx graph load + graphml cache — **needs mirror fallback** |
| `routeiq/graph/poi_finder.py` | OSM feature query — historic subtype allowlist |
| `routeiq/rag/wikipedia_fetcher.py` | Wikipedia enrichment — 15s timeout, "California" suffix |
| `routeiq/facade.py` | Single entry point, generate_narrative() for vector baseline |
| `eval/evaluator.py` | _BAY_AREA_SEED_POIS imported by app.py for vector baseline seeding |
| `docs/learnings.md` | Full learning log — pull into Google Doc |

## How to run

```bash
./restart.sh          # kill + relaunch (preserves cache/graphs/)
python3 -m pytest tests/ -v   # 121 tests
python3 day4_verify.py        # smoke test, no API key needed
```

## Gotchas

- Branch is 1 commit ahead of remote — do NOT push until explicitly asked
- Amend commits for small fixes; new commits for substantive work
- `cache/graphs/` must NOT be deleted — 2-5 min to rebuild per route
- `ox.settings.overpass_url` is the correct OSMnx 2.x attribute (not `overpass_endpoint`)
- Vector narrative adds ~5-10s per query (second Claude call after main pipeline)
- `eval/evaluator._BAY_AREA_SEED_POIS` is imported by app.py — private name, internal use OK
