# Day 5 Handoff — Session 7

**Date:** 2026-06-10
**Branch:** feat/days-1-3-graph-rag-pipeline (up to date with remote)
**Tests:** 121/121 passing

---

## What was built this session

### Animated pipeline stepper (app.py)
- Replaced `st.spinner()` with a vertical 4-step stepper: blinking icon on active step,
  live sub-task message underneath (e.g. "Geocoding San Francisco… → Loading OSM road
  network… → Scanning corridor for POIs…")
- `_render_stepper(state)` — pure function returning HTML/CSS with `@keyframes riq-pulse`
- Callback wired: `facade.run(query, on_progress=_on_progress)`

### Background graph preload (app.py)
- On startup, a daemon thread pre-warms `cache/graphs/` for all 4 demo corridors
- Startup banner: `st.info("🔄 Pre-loading map data…")` while thread is alive
- Bboxes in `_DEMO_BBOXES`: SF→Monterey, SF→Napa, SJ→Santa Cruz, SF→Half Moon Bay

### `on_progress` callback in pipeline (pipeline.py, facade.py)
- `RoutePipeline.__init__` initializes `self._progress = lambda step, sub: None`
- `run(query, on_progress=None)` replaces it per-run
- ~12 sub-step calls across all 4 nodes (parse, graph, rag, narrate)
- `facade.py` threads it through with same signature

### POI data quality fixes
- **poi_finder.py:** `historic: True` → explicit allowlist (`castle`, `fort`, `monument`,
  `memorial`, `ruins`, `archaeological_site`, `lighthouse`, `manor`, `battlefield`)
- **wikipedia_fetcher.py:** opensearch now appends "California" for disambiguation;
  timeout raised 5s → 15s
- **pipeline.py:** removed hard description gate that discarded all POIs when Wikipedia
  enrichment failed — POIs without descriptions are now kept for Claude to handle

### Vector baseline isolation fix (app.py)
- `VectorBaseline` now gets its own `POIIndexer(collection_name="routeiq_vector_baseline")`
  pre-seeded at startup with 15 Bay Area landmark POIs from `eval/evaluator._BAY_AREA_SEED_POIS`
- GraphRAG pipeline uses `shared_indexer` (on-route POIs only)
- Vector baseline searches the broad Bay Area corpus — different stops from GraphRAG ✅

### Dual narrative (facade.py, app.py)
- `facade.generate_narrative(origin, destination, distance_km, drive_time_min, poi_context)`
  exposes NarrativeChain directly for arbitrary POI context
- After each run, vector baseline is queried and a second Claude narrative generated from
  those stops; stored as `state["vector_narrative"]`
- Narrative expander label + content switches based on `view_mode` radio:
  - GraphRAG → "Route narrative — GraphRAG"
  - Vector Baseline → "Route narrative — Vector Baseline"

### docs/learnings.md (new)
- Full learning log covering 4 themes: RAG data quality, KnowledgeRAG design, LangGraph
  pipeline, GraphRAG vs vector finding — ready to pull into the Google Doc

### restart.sh fix
- No longer deletes `cache/graphs/` (expensive parsed graphml files)
- Only clears `~/.cache/osmnx/` (raw Overpass HTTP responses)

---

## Current app state — what works

- `./restart.sh` → starts app with preload banner
- SF→Monterey "coastal history and natural landmarks" → stepper animates, stop cards
  appear with Wikipedia descriptions and thumbnails
- Category filter (historic / tourism / natural) works
- GraphRAG / Vector Baseline toggle shows different stops AND different narrative
- Route narrative expander shows the right narrative for the current mode

---

## What's left — Day 5 (remaining)

### README with architecture diagram
- [ ] `README.md`: Quick Start, Architecture diagram (ASCII or Mermaid), GraphRAG vs
  vector comparison table, tech stack table, how to run
- Reference `docs/learnings.md` for the learning section

### 4 demo queries to test and confirm working
Before recording, verify all 4 produce stop cards (not fallback):
1. `Drive from San Francisco to Monterey, show coastal history and natural landmarks`
2. `Road trip from San Francisco to Napa Valley, show wineries and historic towns`
3. `Drive from San Jose to Santa Cruz, show redwoods and beaches`
4. `Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches`

### Demo recording (≤ 5 min)
- Walk through app live: enter a query, watch stepper, show stop cards + map
- Switch to Vector Baseline: show different stops and different narrative
- Explain the GraphRAG vs vector comparison (use eval/results.md as reference)

### Google Doc
Content to cover (pull from `docs/learnings.md`):
- Project overview and motivation
- Datasets: OSM (road network + POI features) + Wikipedia (landmark descriptions)
- Architecture: 4-node LangGraph pipeline + 3-stage KnowledgeRAG
- Prompts used: QueryParser, NarrativeChain (V1→V2→V3), FallbackChain
- Iterations: the data quality bugs and fixes (use Theme 1 from learnings.md)
- Key learning: GraphRAG vs vector comparison (use final section of learnings.md)

### Submission
- [ ] GitHub link: https://github.com/gayyaswa/routeiq
- [ ] Google Doc link
- [ ] Demo recording link

---

## How to run

```bash
# Start app (kills old server, clears OSMnx HTTP cache, relaunches)
./restart.sh

# Full test suite
python3 -m pytest tests/ -v

# Smoke test (no API key / network needed)
python3 day4_verify.py
```

---

## Key gotchas for next session

- Graph cache is in `./cache/graphs/` — do NOT delete, takes 2-5 min to rebuild
- `@st.cache_resource` caches everything including preload thread — restart server after
  any code change to `_load_resources()` scope
- `eval/evaluator._BAY_AREA_SEED_POIS` is imported by `app.py` — it's a private name
  but internal usage is fine
- Vector narrative is generated at query time (second Claude call after main pipeline);
  adds ~5-10 seconds to each query
- KnowledgeGraph seed has 15 Bay Area POIs — famous landmarks get 3-stage GraphRAG
  treatment; unknown OSM features fall back to vector-only context
- `historic: True` was the root cause of empty POI results — now using explicit subtype
  allowlist in `poi_finder.py`
