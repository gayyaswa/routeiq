# RouteIQ — Session 18 Handoff

**Date:** 2026-06-15  
**Status:** Week 2 fully submitted. Starting Week 3.

---

## Where we are

Week 2 (Graph RAG project) is complete and submitted:
- GitHub repo: clean, all 5 demo routes working from bundled cache
- Google Doc: submitted
- Demo recording: done
- 127/127 tests passing (last verified Session 14; no test-touching changes since)

Latest commit: `2f8c65a` — docs: document POI cache seeding for out-of-area routes

---

## What's in the repo

### Core pipeline
```
routeiq/
  graph/          route_graph.py, poi_finder.py, graph_loader.py, knowledge_graph.py
  routing/        poi_selector.py, detour_scorer.py
  rag/            poi_indexer.py, poi_retriever.py, knowledge_rag.py, vector_baseline.py,
                  wikipedia_fetcher.py, poi_chunker.py
  insights/       query_parser.py, narrative_chain.py, fallback_chain.py
                  prompts/  — system.py, query_parser.py, narrative.py (V3 active), fallback.py
                  examples/ — query_parser_examples.py
  ui/             map_builder.py, card_renderer.py
  facade.py       RouteIQFacade — single entry point
  pipeline.py     LangGraph state machine

eval/             10 Bay Area queries, evaluator.py, results.md (10/10 accuracy)
cache/pois/       bay_area_all.json.gz (984 POIs — primary Bay Area source)
app.py            Streamlit UI — demo hint buttons, cancel, streaming
```

### 5 demo routes (all load from cache instantly)
1. SF → Muir Woods (redwoods, coastal views)
2. SF → Napa Valley (wineries, historic towns)
3. San Jose → Santa Cruz (redwoods, beaches)
4. SF → Half Moon Bay (coastal cliffs, beaches)
5. SF → Sausalito via Golden Gate Bridge (historic sites, bay views)

---

## Git state at handoff

**Modified (not committed):** ChromaDB binary files — normal from running the app, fine to leave.

**Untracked POI caches** — generated from testing out-of-area routes:
```
cache/pois/pois_n33.539_*.json.gz    # AZ — Phoenix/Tempe
cache/pois/pois_n33.540_*.json.gz    # AZ — Phoenix
cache/pois/pois_n34.143_*.json.gz    # LA
cache/pois/pois_n35.244_*.json       # Flagstaff (uncompressed — 4x larger than .gz)
cache/pois/pois_n36.156_*.json.gz    # Las Vegas
cache/pois/pois_n36.248_*.json.gz    # Hoover Dam / Nevada
```
These are useful if Week 3 expands to multi-region. Commit or `.gitignore` as needed.

---

## Known issues / deferred work

| Issue | Detail |
|---|---|
| Preferences don't filter POIs | QueryParser outputs NL keywords (`"redwoods"`); POISelector expects OSM categories (`"natural"`). Silent fallback = all POIs always. Fix: update QUERY_PARSER_PROMPT to output OSM category names. |
| Texas examples in query_parser_examples.py | 2 of 5 few-shot examples are Texas routes — never cleaned up. Low priority. |
| Flagstaff cache is uncompressed | `pois_n35.244*.json` is uncompressed — should be `.json.gz`. |

---

## Week 3

`docs/Week 3 Project Handout_ Agentic AI Systems.docx` is in the repo — **read this first** to understand the new assignment before planning any changes.

---

## Key architecture reminders

- **Two ChromaDB collections:** `routeiq_pois` (GraphRAG per-route) + `routeiq_vector_baseline` (95 Bay Area POIs)
- **KnowledgeRAG** uses collection `routeiq_chunks` (chunked Wikipedia text)
- **POI ranking:** `(0 if wikipedia_tag else 1, -scenic_score, detour_min)` + 2 km spread
- **OSMnx 2.x bbox convention:** `(west, south, east, north)` — opposite of 1.x
- **`@st.cache_resource`** holds Facade/pipeline — must restart Streamlit after code changes
- **Overpass mirror kumi.systems** consistently times out — it's last in the list intentionally
- **Golden Gate Bridge** osm_id is assigned to Sausalito (not SF) — correct, GGB is geographically closer to Sausalito centroid

---

## How to run

```bash
# Install deps
pip install -r requirements.txt

# Run app
streamlit run app.py

# Tests
python3 -m pytest tests/ -v
```

`ANTHROPIC_API_KEY` must be set in `.env` (see `.env.example`).
