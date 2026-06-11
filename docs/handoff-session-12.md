# Session 12 Handoff — POI Quality, Image Fixes, Overpass Error Handling

**Date:** 2026-06-10
**Branch:** feat/days-1-3-graph-rag-pipeline
**Status:** 127/127 tests passing

---

## What we did this session

### 1. Wikipedia enrichment — two root-cause fixes (`routeiq/rag/wikipedia_fetcher.py`)

**Fix 1 — 403 Forbidden (all enrichment silently failing)**
Wikipedia's API blocks requests with no `User-Agent` header with HTTP 403. Every fetch
failed silently inside `except Exception: pass`, so ALL POIs had empty `description` and
`image_url`. Fixed by setting `User-Agent: RouteIQ/1.0 (scenic route assistant; guruplace04@gmail.com)`
on the session at construction time.

**Fix 2 — "California" suffix broke exact name searches**
The opensearch fallback was appending "California" to every POI name.
`"Pigeon Point Lighthouse California"` → 0 results. `"Pigeon Point Lighthouse"` → correct article.
Fixed: try bare name first; fall back to `"<name> California"` only if bare search returns nothing.

---

### 2. POI selection overhaul (`routeiq/routing/poi_selector.py`, `routeiq/graph/poi.py`, `routeiq/graph/poi_finder.py`)

**Problem:** "San Francisco" geocodes to Union Square downtown. The A* path through downtown
picks up 5 obscure street monuments (all 0-min detour) and crowds out the Golden Gate Bridge.

**Fix 1 — Geographic spread (2 km minimum between selected POIs)**
Greedy selection: each candidate must be ≥ 2 km from every already-selected POI. Prevents
filling all 5 slots from one neighbourhood.

**Fix 2 — Three-tier sort: notability → scenic score → detour**
- **Tier 1:** OSM `wikipedia_tag` presence — crowd-sourced notability signal. POIs with it
  (Golden Gate Bridge, Fort Point, Lone Sailor Monument) claim their geographic slots before
  untagged plaques do.
- **Tier 2:** Scenic/experiential score per OSM subtype (viewpoint=9, beach=9, lighthouse=8,
  fort=7, attraction=7, memorial=3, etc.). A waterfall at 5-min detour beats a plaque at 0-min.
- **Tier 3:** detour_min — tiebreaker within equally notable, equally scenic POIs.

**`poi.py`:** Added `subtype: str | None = None` field (OSM value: "viewpoint", "beach", "fort", etc.)
**`poi_finder.py`:** Captures the specific OSM value and stores it in `poi.subtype`.

**Cache note:** Existing `cache/pois/*.json` files have no `subtype` key — POIs loaded from old
caches default to `subtype=None` (scenic score = 5). Delete cache files to get full benefit:
```bash
rm cache/pois/*.json
```

**Result:** SF→Sausalito now returns Fort Point, Warden's House, Coit Tower, Lone Sailor
Monument — a real spread across the corridor instead of 5 downtown plaques.

---

### 3. Vector Baseline images (`routeiq/rag/vector_baseline.py`, `app.py`)

**Problem:** Vector Baseline cards always showed placeholder grey boxes. Two causes:
1. `VectorBaseline.query()` didn't return `image_url` from ChromaDB metadata (it was stored, just not read back).
2. Seed POIs in `_BAY_AREA_SEED_POIS` had no `image_url` (Wikipedia never called for them).

**Fix:** `VectorBaseline.query()` now includes `image_url` in results.
`app.py` `_load_heavy()`: checks if existing seed collection has empty `image_url`; if so,
enriches all 15 seed POIs with `WikipediaFetcher` in parallel (ThreadPoolExecutor) before
upserting them. One-time cost per server restart.

---

### 4. Image modal popup (`routeiq/ui/card_renderer.py`, `app.py`)

`IMAGE_MODAL_HTML` — a `position:fixed` dark overlay covering the entire iframe viewport.
Clicking any card image with a real URL shows it enlarged. Press Esc or click anywhere to close.
Placeholder images (grey SVG) are not clickable.

Implementation: `_img_tag(src, zoom_src=None)` — adds `onclick="riShow(url)"` and `cursor:zoom-in`
when `zoom_src` is provided. `onerror` removes the click handler if the image fails to load.
`IMAGE_MODAL_HTML` is appended once per cards container (outside the scrollable div).

---

### 5. Route Narrative auto-expands (`app.py`)

Changed `st.expander(narrative_label, expanded=False)` → `expanded=True`. Narrative is open
immediately after results render; user can collapse manually.

---

### 6. Overpass failure UX (`routeiq/graph/poi_finder.py`, `routeiq/pipeline.py`)

**Problem:** When all 4 Overpass mirrors timed out (30s each = 2 min total), the UI was
frozen on "Scanning route corridor…" with no feedback. Then the error message blamed
"category filters" or "data gaps" — Claude fabricating a reason.

**Fix 1 — Live progress during mirror cascade**
`find_pois(progress_fn=None)` — optional callback called at each mirror attempt:
- `"Querying POI server 1/4…"` at start of each attempt
- `"POI server 1/4 timed out — trying backup…"` on timeout
- `"POI server 1/4 unavailable — trying backup…"` on error

**Fix 2 — Typed exception instead of silent `[]`**
`OverpassUnavailableError` raised when all mirrors fail. Distinct from `[]` (successful
query, no POIs in area). `_graph_node` catches it and returns `error: "overpass_unavailable"`
with accurate fallback_reason: *"The OpenStreetMap POI server is temporarily unavailable —
all mirrors timed out. This is a transient outage, not a problem with your query."*

---

### 7. New demo route — Golden Gate Bridge corridor (`app.py`)

Added SF → Sausalito bbox to `_DEMO_BBOXES` for background preloading.
Query: `Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views`

---

### 8. Docs (`docs/learnings.md`)

Three new entries added:
- *OSM `wikipedia` tag as notability proxy*
- *Scenic subtype score — detour cost is not scenic value*
- *KnowledgeGraph centrality as a future popularity signal (deferred)*

---

## Files changed this session

| File | Change |
|---|---|
| `routeiq/rag/wikipedia_fetcher.py` | User-Agent header fix; try bare name before "California" suffix |
| `routeiq/graph/poi.py` | Added `subtype: str \| None = None` field |
| `routeiq/graph/poi_finder.py` | Populate `subtype`; `progress_fn` callback; `OverpassUnavailableError` |
| `routeiq/routing/poi_selector.py` | 3-tier sort (notability, scenic score, detour); scenic score table; geographic spread |
| `routeiq/pipeline.py` | Pass `progress_fn` to `find_pois`; catch `OverpassUnavailableError` |
| `routeiq/rag/vector_baseline.py` | Return `image_url` from Chroma metadata |
| `routeiq/ui/card_renderer.py` | `IMAGE_MODAL_HTML`; `_img_tag` zoom support; vector card uses `image_url` |
| `app.py` | SF→Sausalito bbox; IMAGE_MODAL_HTML wired; narrative `expanded=True`; seed POI enrichment |
| `docs/learnings.md` | 3 new POI selection entries |
| `tests/test_poi_finder.py` | Updated for `subtype`, `OverpassUnavailableError`, `progress_fn` |
| `tests/test_poi_selector.py` | Updated coords for spread; geographic spread test |

---

## What's still next (Day 5 remaining)

- [ ] `rm cache/pois/*.json` → test all 5 demo queries with fresh subtype-aware caches
- [ ] Record demo video (≤ 5 min): live walkthrough + GraphRAG vs Vector comparison
- [ ] Google Doc: pull from `docs/learnings.md` + `prompts.md` + `eval/results.md`
- [ ] Push branch to remote + submit: GitHub link + Google Doc + recording

### 5 demo queries (4 original + Golden Gate)
1. `Drive from San Francisco to Monterey, show coastal history and natural landmarks`
2. `Road trip from San Francisco to Napa Valley, show wineries and historic towns`
3. `Drive from San Jose to Santa Cruz, show redwoods and beaches`
4. `Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches`
5. `Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views`

---

## Key gotchas carried forward

- Old `cache/pois/*.json` files have no `subtype` — delete them to get scenic scoring
- `@st.cache_resource` holds instances — restart Streamlit after any code change
- Wikipedia 403 was root cause of all empty descriptions/images (now fixed via User-Agent)
- `OverpassUnavailableError` is distinct from empty POI list — check error type in tests
- Vector Baseline seed enrichment runs once per server start (checks `image_url` in first Chroma doc)
- KnowledgeGraph centrality for POI selection is documented as Week 2 future work in `docs/learnings.md`
