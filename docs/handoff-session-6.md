# Day 4 Handoff — Session 6

**Date:** 2026-06-09  
**Branch:** feat/days-1-3-graph-rag-pipeline (same branch, Day 4 files added)

## What was built this session

### UI layer (new)
- `routeiq/ui/__init__.py` — `MapBuilder`, `CATEGORY_COLORS` dict (single source of truth)
- `routeiq/ui/map_builder.py` — `MapBuilder.build(route_result, top_pois, filtered_categories?)` → `folium.Map`
  - CartoDB Positron tiles, AntPath animated route, color-coded CircleMarkers
  - Colors: historic=#c0392b, tourism=#2980b9, natural=#27ae60
- `routeiq/ui/card_renderer.py` — `render_stop_card(sp, rank) → str` (Bootstrap-style HTML)
  - Category badge, name, `+N min detour`, Wikipedia thumbnail, 2-line description
- `app.py` — Streamlit entry point
  - `st.set_page_config(layout="wide")`, query input, spinner
  - 2-column: `st_folium(map, height=500)` left | HTML stop cards right
  - Category multiselect filter, GraphRAG vs Vector Baseline radio toggle
  - Route stats bar (origin → destination, km, min, stop count)
  - Narrative in `st.expander`
  - Error path: shows fallback narrative as warning banner

### Evaluation layer (new)
- `eval/__init__.py`
- `eval/eval_queries.py` — 10 Bay Area queries (6 route + 4 semantic)
- `eval/evaluator.py` — `Evaluator` class, 15 Bay Area seed POIs, GraphRAG + vector runners
- `eval/run_eval.py` — CLI: runs all 10 queries, prints + saves results table
- `eval/results.md` — pre-captured results (10/10 prediction accuracy)

### Bug fixes
- `routeiq/insights/query_parser.py` — strip markdown code fences before JSON parse
  (LLM wraps JSON in ```json blocks; added `re.sub` to strip before `json.loads()`)

### New dependency
- `scikit-learn` added to `requirements.txt` (required by OSMnx `nearest_nodes` on unprojected graphs)
- `streamlit` added to `requirements.txt` (was implicit via `streamlit-folium`, now explicit)

### Smoke test
- `day4_verify.py` — verifies MapBuilder, card_renderer, category filter, CATEGORY_COLORS consistency

## Evaluation results summary

**10/10 prediction accuracy.** GraphRAG won all 6 route queries; Vector won all 4 semantic queries.

**Key finding (nuanced):**
- GraphRAG finds the *actual on-route OSM features* — geographic precision, but OSM data quality varies
  (route POIs included highway markers, urban artworks, and small local POIs alongside famous landmarks)
- Vector finds the *famous landmarks* by semantic similarity — but they may not be on the exact route
- **GraphRAG win condition:** user specifies a route (A → B) — constraints eliminate off-route false positives
- **Vector win condition:** open-ended query ("best X near Y") — no route to constrain

This finding is perfect for the Google Doc: it's an honest nuanced comparison showing both strengths.

## Day 5 demo routes (updated to Bay Area)

1. SF → Monterey (coastal: Cannery Row, 17-Mile Drive, Point Lobos)
2. SF → Napa Valley (wine: wineries, Yountville, Castello di Amorosa)  
3. San Jose → Santa Cruz (redwoods: Henry Cowell, Roaring Camp Railroad)
4. SF → Half Moon Bay (coastal: Mavericks, Pescadero, Pigeon Point Lighthouse)

## How to run

```bash
# Streamlit app
export ANTHROPIC_API_KEY=...
streamlit run app.py

# Evaluation (live, ~15 min)
python3 eval/run_eval.py

# Smoke test (no API key, no network)
python3 day4_verify.py

# Full test suite
python3 -m pytest tests/ -v
```

## Test status

121/121 tests pass. No regressions from Day 4 additions.

## What's left — Day 5

- [ ] README with architecture diagram
- [ ] Demo prep: 4 canned Bay Area queries tested and working in `streamlit run app.py`
- [ ] Record demo (≤ 5 min): live app walkthrough + explain GraphRAG vs vector comparison
- [ ] Google Doc: project overview, datasets (OSM + Wikipedia), prompts used, iterations, key learning
- [ ] Submit: GitHub link + Google Doc + demo recording

## Key gotchas for next session

- `scikit-learn` must be installed (`pip3 install scikit-learn`) for OSMnx to work
- Query parser strips markdown code fences — fix is in `query_parser.py`
- OSMnx graph loads take 30-60s per route (cached to `./cache/` after first load)
- VectorBaseline shares the same ChromaDB collection as POIIndexer — accumulates across queries in same session
- The eval script uses `_ensure_seeded()` to pre-populate ChromaDB with Bay Area POIs before running queries
