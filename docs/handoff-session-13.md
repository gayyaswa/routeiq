# Session 13 Handoff — POI Master Cache, Route Swap, Vector Gate, Doc Plan

**Date:** 2026-06-10
**Branch:** feat/days-1-3-graph-rag-pipeline
**Status:** 127/127 tests passing — 2 commits ahead of previous session

---

## What we did this session

### 1. Replaced SF → Monterey with SF → Muir Woods (`app.py`)

SF → Monterey had a huge bbox (1.4° lat × 0.9° lon) — slow Overpass query and no POI
cache. Replaced with SF → Muir Woods (Golden Gate / Marin Headlands / redwoods).

`_DEMO_BBOXES[0]` changed:
```
before: dict(north=37.9,  south=36.5, east=-121.7, west=-122.6)  # SF → Monterey
after:  dict(north=38.00, south=37.67, east=-122.32, west=-122.63) # SF → Muir Woods
```

Demo query: `Drive from San Francisco to Muir Woods, show redwoods and coastal views`

---

### 2. Bay Area POI master cache — zero Overpass at demo time

**Architecture change:** `POIFinder.find_pois()` now has three lookup paths:

1. **`cache/pois/bay_area_all.json.gz`** (primary) — load 984 Bay Area POIs, in-memory
   Shapely spatial filter to route buffer. Zero Overpass call. ~0.1s.
2. **Per-route `.json.gz` / `.json`** (fallback) — legacy per-route caches for uncached
   non-Bay-Area routes. New Overpass results write `.json.gz`; old `.json` still readable.
3. **Live Overpass** (last resort) — only when neither cache exists. Mirror fallback
   + progress_fn callbacks unchanged.

`_filter_master()` returns `None` on empty result (route outside Bay Area coverage) so
non-Bay-Area routes correctly fall through to per-route cache or Overpass.

**Files changed:**
- `routeiq/graph/poi_finder.py` — master file check, `.json.gz` read/write, `_filter_master()`, `_query_overpass()` refactored out
- `scripts/seed_poi_cache.py` — two modes: `bootstrap` (merges existing per-route JSONs, default) and `--tiles` (full 4-tile Overpass fetch)
- `.gitignore` — added `cache/graphs/`, `cache/chroma/`, `cache/osmnx/`, `cache/*.json`; `cache/pois/` intentionally not ignored
- `app.py` — Muir Woods bbox

**Committed artifacts:**
- `cache/pois/bay_area_all.json.gz` — 984 unique POIs, **33 KB** gzip
- 6 per-route `.json` cache files for all 5 demo corridors
- `docs/plan-poi-master-cache.md` — strategy doc with OSM graph TODO

**To regenerate master file:**
```bash
python3 scripts/seed_poi_cache.py          # bootstrap from existing per-route JSONs
python3 scripts/seed_poi_cache.py --tiles  # full Overpass fetch (takes 3-5 min)
```

---

### 3. Vector Baseline geographic gate (`app.py`)

**Bug fixed:** For routes outside Bay Area (e.g. Sedona → Flagstaff), `VectorBaseline`
returned Bay Area seed POIs (wrong geography). Claude then correctly flagged the mismatch
("outside California"). Both symptoms from the same root cause.

**Fix:** `_VECTOR_BASELINE_BBOX` constant + `_route_in_vector_coverage(route_result)` helper.
- Card panel: shows `"Vector Baseline covers Bay Area demo routes only. GraphRAG works for any region."` — no query runs
- Narrative: shows GraphRAG narrative + caption note instead of confused Claude narrative

GraphRAG path unaffected — works for any region.

---

### 4. Google Doc plan (`docs/plan-poi-master-cache.md` → approved plan file)

Planned the Week 2 submission Google Doc. Follows handout guidelines exactly.
7 sections (one-liner, datasets, 3 RAG approaches, narration+prompts, evaluation,
iterations, learnings). Key decisions:
- Include all prompts verbatim (system, query parser V1, narrative V1→V2→V3)
- Evaluation table from `eval/results.md` included verbatim
- Skip: session chronology, performance tuning internals, code design patterns

---

## Files changed this session

| File | Change |
|---|---|
| `app.py` | Muir Woods bbox; `_VECTOR_BASELINE_BBOX`; `_route_in_vector_coverage()`; vector card + narrative geographic gate |
| `routeiq/graph/poi_finder.py` | Master file lookup (Path 1); `.json.gz` per-route write (Path 2); `_filter_master()` / `_query_overpass()` split; legacy `.json` read preserved |
| `.gitignore` | `cache/graphs/`, `cache/chroma/`, `cache/osmnx/`, `cache/*.json` ignored; `cache/pois/` not ignored |
| `scripts/seed_poi_cache.py` | Bootstrap + tile fetch modes; handles `.json.gz` and `.json`; Bay Area bbox filter |
| `cache/pois/bay_area_all.json.gz` | NEW — 984 POIs, 33 KB, committed |
| `cache/pois/pois_n37.*.json` (6 files) | NEW — per-route cache for all 5 demo routes, committed |
| `docs/plan-poi-master-cache.md` | NEW — strategy doc |

---

## Commits this session

```
e558024  feat: pre-cached Bay Area POI master file — zero Overpass calls at demo time
2e624a6  fix: vector baseline geographic gate — no Bay Area POIs for non-Bay-Area routes
```

---

## What's next — Day 5 remaining

- [ ] **Smoke test** all 5 demo routes in live app — confirm master cache hits, no Overpass in logs, stop cards render with images
- [ ] **Google Doc** — write using approved plan (`plan-poi-master-cache.md`):
  - 7 sections: one-liner, datasets, 3 RAG approaches, narration+prompts, eval, iterations, learnings
  - Include all prompts verbatim (system, query parser, narrative V1→V2→V3)
  - Pull eval table from `eval/results.md` verbatim
- [ ] **Record demo video** (≤ 5 min): query → stepper → map + cards → GraphRAG vs Vector tab → narrative
- [ ] **Push branch + submit**: GitHub link + Google Doc + recording

### 5 demo queries

1. `Drive from San Francisco to Muir Woods, show redwoods and coastal views`
2. `Road trip from San Francisco to Napa Valley, show wineries and historic towns`
3. `Drive from San Jose to Santa Cruz, show redwoods and beaches`
4. `Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches`
5. `Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views`

---

## Key gotchas carried forward

- `bay_area_all.json.gz` is 984 POIs from bootstrap (5 corridor JSON merges) — run `--tiles` for broader coverage
- Old `cache/pois/*.json` files have no `subtype` key — POIs loaded from them get `subtype=None` (scenic score = 5)
- `_filter_master()` returns `None` (not `[]`) on empty result — caller checks `if result is not None`
- Vector Baseline geographic gate checks route midpoint, not origin/destination — midpoint is more robust for long routes
- `@st.cache_resource` holds instances — restart Streamlit after any code change
- Arizona test left `pois_n35.244_s34.824_e-111.606_w-111.806.json` in `cache/pois/` — not committed, not gitignored (can delete)
