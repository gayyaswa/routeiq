# Session 14 Handoff — Bay Area KG, Enriched Vector Baseline, Eval Refresh, Google Doc

**Date:** 2026-06-10
**Branch:** feat/days-1-3-graph-rag-pipeline — pushed to remote
**Status:** 127/127 tests passing — 1 new commit pushed

---

## What we did this session

### 1. KnowledgeGraph data — Texas → Bay Area (critical bug fix)

`knowledge_graph_data.py` was seeded with Texas POIs (Austin, San Antonio, Hill Country).
All demo routes are Bay Area. Result: `get_pois_for_route()` returned empty set for every
Bay Area route → stage 2 filtered all candidates → KnowledgeRAG silently returned `""` →
V3 narrative prompt fired with empty KG context. The KG enrichment was doing nothing.

**Fix:**
- Replaced Texas POIS/CITIES/REGIONS/RELATIONSHIPS with Bay Area equivalents
- `_load_notable_bay_area_pois()` auto-loads 95 OSM-verified notable POIs from
  `bay_area_all.json.gz` (wikipedia_tag filtered), nearest-city assigned via haversine
- 10 Bay Area cities: SF, Oakland, Berkeley, San Jose, Santa Cruz, Sausalito, Napa,
  Half Moon Bay, Mill Valley, Tiburon
- 7 regions: San Francisco, North Bay/Marin, East Bay, Peninsula, South Bay, Wine Country, Bay Area
- RELATIONSHIPS auto-generated: LOCATED_IN, HAS_CATEGORY, IN_REGION (city→region + city→Bay Area)
- Fallback to 4 hardcoded anchor POIs if master cache missing (test stability)

**V3 prompt now fires correctly** — Claude gets `city | region | nearby stops | description`
for all 95 notable POIs in the master cache that appear on demo routes.

**KG gotcha:** Golden Gate Bridge (`('way', 370672707)`, lat 37.82) is nearest-city
assigned to **Sausalito**, not San Francisco — the GGB spans the strait and its OSM centroid
is closer to the Sausalito city node. Coit Tower is the reliable SF anchor.

**Tests updated:**
- `tests/test_knowledge_graph.py`: migrated from `kg_alamo`/Austin→SA to Bay Area anchors
  (Coit Tower = `('way', 28824850)`, Fort Point = `('relation', 5504536)`, GGB, Palace of Fine Arts)
- `tests/test_knowledge_rag.py`: migrated from `kg_alamo`/Austin→SA route to Coit Tower/Fort Point
  + SF→Sausalito route coords

---

### 2. Vector baseline — 15 stale POIs → 95 enriched notable POIs

`_BAY_AREA_SEED_POIS` in `eval/evaluator.py` was 15 hardcoded POIs including Monterey-area
POIs (Cannery Row, 17-Mile Drive) irrelevant to current demo routes.

**Fix:**
- Added `_load_notable_bay_area_pois()` — loads 95 wikipedia-tagged POIs from master cache
- `_BAY_AREA_SEED_POIS = _load_notable_bay_area_pois()` — dynamic, always current
- `_ensure_seeded()` now Wikipedia-enriches all 95 POIs (parallel, 5 threads) before indexing
  (91/95 had Wikipedia articles)
- `app.py`: re-seed trigger changed from `count == 0` to `count < len(seed) // 2` — handles
  upgrade from old 15-POI collection automatically on next app start

---

### 3. Eval queries updated + eval re-run

`eval/eval_queries.py`:
- Route 1: SF→Monterey → **SF→Muir Woods** (matches demo route 1)
- Route 6: Oakland→Muir Woods → **SF→Sausalito via Golden Gate Bridge** (matches demo route 5)

`eval/run_eval.py`:
- Semantic query label fixed: `*(pipeline error)*` → `*(semantic — no route to parse)*`

**Fresh eval results:** 10/10 prediction accuracy — GraphRAG wins 6/6 route queries,
Vector wins 4/4 semantic queries. `eval/results.md` auto-updated.

---

### 4. Google Doc draft written

`docs/google-doc-draft.md` — full 7-section submission doc:
1. Project Overview (one-liner + pipeline diagram)
2. Datasets (OSM + Wikipedia + KG — updated to 95 POIs / 10 cities / 7 regions)
3. Three RAG Approaches (Vector / GraphRAG / KG RAG — all verbatim architecture)
4. Narration + Generation (system prompt + query parser V1 + narrative V1→V2→V3, verbatim)
5. Evaluation (fresh 10-query table from eval/results.md)
6. Iterations (7 iterations including KG data bug as iteration 7)
7. Key Learnings (6 bullets)

---

### 5. README + learnings.md stale stats fixed

All `15 POIs / 8 cities / 4 regions / 20+ nodes` references updated to
`95 POIs / 10 cities / 7 regions / 112+ nodes`. SF→Monterey example in README
updated to SF→Muir Woods. Evaluation section added to README with run instructions.

---

## Files changed this session

| File | Change |
|------|--------|
| `routeiq/graph/knowledge_graph_data.py` | Full rewrite — Texas → Bay Area, auto-loads from master cache |
| `eval/evaluator.py` | _load_notable_bay_area_pois() replaces hardcoded list; _ensure_seeded() enriches |
| `eval/eval_queries.py` | Routes 1 + 6 updated to match demo routes |
| `eval/run_eval.py` | Semantic query label fixed |
| `eval/results.md` | Regenerated — 10/10, Bay Area routes, 91-POI vector baseline |
| `app.py` | Re-seed trigger updated for 95-POI upgrade |
| `tests/test_knowledge_graph.py` | Migrated to Bay Area anchors |
| `tests/test_knowledge_rag.py` | Migrated to Bay Area anchors + SF→Sausalito route |
| `docs/google-doc-draft.md` | NEW — full 7-section submission doc |
| `docs/learnings.md` | KG stats updated (95 POIs / 10 cities / 7 regions) |
| `README.md` | Evaluation section added; test count 127; SF→Muir Woods example |

---

## Commit this session

```
8ad448c  feat: Bay Area KG + enriched vector baseline + updated eval + Google Doc draft
```

---

## What's next — Day 5 remaining

- [ ] **Smoke test** — run 5 demo routes live (app should auto-reseed Chroma vector baseline
  with 95 POIs on first query; ChromaDB routeiq_vector_baseline collection will expand)
- [ ] **Copy `docs/google-doc-draft.md` into Google Docs** — format, add screenshots
- [ ] **Record demo video** (≤ 5 min):
  - Run a demo query → show stepper → map + stop cards with Wikipedia images
  - Show GraphRAG vs Vector tab comparison
  - Briefly explain why GraphRAG wins on route queries, vector wins on semantic queries
- [ ] **Submit**: GitHub repo link + Google Doc link + recording

### 5 demo queries
1. `Drive from San Francisco to Muir Woods, show redwoods and coastal views`
2. `Road trip from San Francisco to Napa Valley, show wineries and historic towns`
3. `Drive from San Jose to Santa Cruz, show redwoods and beaches`
4. `Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches`
5. `Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views`

---

## Key gotchas carried forward

- `bay_area_all.json.gz` — 984 POIs; master source for both POIFinder and KG seed
- KG auto-loads at import time from master cache — no manual seeding needed
- Golden Gate Bridge osm_id nearest-city = Sausalito (not SF) due to lat 37.82 being closer
  to Sausalito city node — use Coit Tower as SF anchor in tests
- Chroma `routeiq_vector_baseline` will re-seed automatically (count < 95//2 = 47 check)
  on first `_load_heavy()` call — takes ~40-60s, happens once
- `@st.cache_resource` persists across requests — restart Streamlit if code changes
- Arizona test file `pois_n35.244*.json` still in `cache/pois/` — untracked, safe to delete
- `eval/run_eval.py` semantic label now reads `*(semantic — no route to parse)*` not `*(pipeline error)*`
