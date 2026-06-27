# Handoff — Session 47

**Date:** 2026-06-25
**Branch:** main
**Status:** Presentation-ready. New `query_poi_context` tool live. README fully updated. All committed and pushed.

---

## What was done this session

### 1. Group presentation framework created ✅

Built `docs/presentation-framework.html` — copy-paste into Google Docs for the group presentation. Covers:

- **Use case:** spatial + semantic alignment problem — stops must be geographically reachable AND semantically relevant
- **Where RAG fits:** 4-layer table (Knowledge Graph RAG, Live RAG, Vector RAG + KG enrichment, direct fetch)
- **Tools the agent calls:** 7-tool table with what each does
- **Autonomy vs workflow:** workflow = fixed pipeline shape; autonomy = tool selection inside ReAct loop; human-in-the-loop = `interrupt()` before narrate
- **Evaluation:** 5-config × 15-query results table, 5 metrics listed, honest gap (geographic proximity not measured)
- **Multi-agent roadmap:** OrchestratorAgent → DayTripAgent + RestaurantAgent + LodgingAgent

Key clarification made during prep: "Routing: 15/15" in eval results means **tool routing** (did agent pick right first tool), not geographic proximity. That gap was acknowledged and added to the HTML.

### 2. RAG architecture clarified ✅

Investigated which RAG layers actually apply to each tab:

| Tab | Wikipedia path | ChromaDB/Vector RAG | Knowledge RAG |
|-----|---------------|--------------------|----|
| Day Trip Planner (before this session) | Direct fetch → into LLM prompt | ❌ not used | KG lookup only via `find_city_pois` |
| Route Planner | Fetch → embed → ChromaDB → semantic retrieval | ✅ `KnowledgeRAG` 3-stage | ✅ Stage 2 KG augment |

Tavily activity classifier confirmed as Live RAG: 1 web search per `(city, activity)` → LLM extracts matched POI names across full candidate list (bulk, not per-POI). 21-day cache; degrades gracefully on empty key.

### 3. New tool: `query_poi_context` ✅

**File:** `routeiq/agent/tools/query_poi_context.py`

Adds Vector RAG + KG enrichment to the Day Trip Planner. Called after `rate_pois` as step 3.

**What it does:**
1. Parses `rate_pois` JSON output into POI objects
2. Creates ephemeral ChromaDB client + uuid4 collection name (avoids `InternalError: Collection already exists` on repeated calls)
3. Uses `POIChunker.chunk_and_index(pois)` — splits 500-char Wikipedia descriptions into 250-char overlapping chunks, indexes all
4. Calls `KnowledgeRAG.query(preferences, route_coords=[])` — `route_coords=[]` triggers `no_route_specified=True` (line 68 of `knowledge_rag.py`), skipping bbox filter so all candidates get KG enrichment
5. Returns context string: `name | category | city | region | nearby: X, Y, Z | Wikipedia evidence`

**Files changed:**
- `routeiq/agent/tools/query_poi_context.py` — new file
- `routeiq/agent/tools/__init__.py` — added to `ALL_TOOLS` (now 7 tools)
- `routeiq/agent/day_trip_agent.py` — added `"query_poi_context": "rag"` to `_TOOL_TO_STEP`
- `routeiq/insights/prompts/day_trip_planner.py` — V3 prompt: step 3 added; `why_visit` instruction updated to prefer `query_poi_context` evidence; `_SYSTEM` updated

**Prompt versions now:**
- V1 — basic (find → rate → enrich → estimate)
- V2 — two-track activity-aware (select_pois_for_day → rate_pois)
- V3 — adds query_poi_context as step 3 ← **active**

**Note:** `query_poi_context` does not have a dedicated test file. Existing `tests/test_knowledge_rag.py` covers the underlying `KnowledgeRAG` pipeline it calls. Smoke-tested manually during implementation — passes with real POI data.

### 4. README fully overhauled ✅

Two passes of fixes. All stale content removed:

**Pass 1 (from plan):**
- Tagline: added "activity-matched" + "4-layer RAG"
- Env vars: fixed `ACTIVITY_CLASSIFIER` → `ACTIVITY_PROVIDER`; added `TAVILY_API_KEY`, `TRIPADVISOR_API_KEY`
- Agent flow diagram: updated to V3 tool call order
- New RAG Layers section (4-row table)
- Module Layout Mermaid: `5 tools` → `7 tools`
- Project Structure: added `query_poi_context.py`, `tavily_enrichment.py`
- Eval table: `Routing` → `Tool Routing`
- Eval section: added LLM-as-judge `avg_match_quality` mention
- Testing table: added `query_poi_context` row

**Pass 2 (additional stale content found):**
- "What It Does": `five tools` → `seven tools`
- Ratings Layer: removed "primary — key pending" from TripAdvisor; added `TavilyEnrichmentProvider`; corrected provider order (recommended → fallback)
- Module Layout Mermaid: added `activities/` node + `AC` wired from `AG`; added `poi_chunker` to `rag/`; added `activity_poi_selector` to `routing/`; added `AG → RA` edge (agent now uses RAG via `query_poi_context`)
- Key findings text: "Routing 15/15" → "Tool routing 15/15"
- Design Patterns: added `ActivityClassifier` Strategy (OSM + Tavily); added `ActivityClassifierFactory`

### 5. Bug fix: RatingsFactory default ✅

**File:** `routeiq/ratings/factory.py` line 24

**Before:** `os.getenv("RATING_PROVIDER", "foursquare")` — if no `.env` file, defaults to `foursquare` → no key → `_NullRatingProvider` → no ratings

**After:** `os.getenv("RATING_PROVIDER", "llm_synthetic")` — zero-config clones get LLM synthetic ratings (fully offline, caches pre-committed)

**Test updated:** `tests/ratings/test_factory.py` — renamed `test_missing_api_key_env_var_returns_null_provider` → `test_no_rating_provider_env_defaults_to_llm_synthetic`; asserts `LLMSyntheticRatingProvider` instead of `_NullRatingProvider`

### 6. Cache & key degradation behavior documented ✅

| Provider | Without key | Cache committed? |
|----------|------------|-----------------|
| Tavily activity classifier | Instantiated with `api_key=""`; cache hits work; misses degrade to `[]` → scenic fallback | ✅ 12 files (SF + NYC, 6 activities each) |
| TripAdvisor ratings | Factory returns `_NullRatingProvider` immediately — 790 committed cache files bypassed | ✅ 790 files (but inaccessible without key) |
| LLM synthetic ratings | No key needed | ✅ SF, Oakland, Berkeley, San Jose, NYC, Chicago, Seattle, Austin |

**Recommendation for team members without keys:** use defaults (`RATING_PROVIDER=llm_synthetic`, `ACTIVITY_PROVIDER=osm`). Fully offline, all Bay Area cities pre-cached.

---

## Commits this session

| Hash | Message |
|------|---------|
| `8dd5cd6` | feat: add query_poi_context tool + update README + fix factory default |

---

## Current state

- **Branch:** `main`
- **Tests:** 315/315 passing
- **Git:** clean
- **Presentation doc:** `docs/presentation-framework.html` — open in browser, Cmd+A, paste into Google Docs
- **New tool live:** `query_poi_context` in `ALL_TOOLS`, wired to Prompt V3

---

## What's next

### Multi-agent expansion (Week 5 roadmap)

Architecture designed this session (see `docs/presentation-framework.html` Roadmap section):

```
OrchestratorAgent
├── DayTripAgent     (existing)  → itinerary + POIs
├── RestaurantAgent  (new)       → meal stops near each POI
└── LodgingAgent     (new)       → hotel search + booking links
```

**RestaurantAgent tools to add:**
- `find_restaurants_near_stop` — Yelp Fusion / Google Places within 500m of each stop
- `rank_by_cuisine_match` — match user preferences from original NL query
- `check_hours` — filter closed spots at planned visit time

**LodgingAgent tools to add:**
- `search_hotels_in_city` — Booking.com / SerpAPI hotel search
- `filter_by_budget_proximity` — price range + walking distance to next-day start
- `generate_booking_link` — deep-link (no live reservation needed to start)

**New eval metrics for multi-agent:**
- Inter-agent coherence — restaurant fits the DayTripAgent time slot
- Constraint propagation — budget cap flows across all agents
- Parallelization gain — RestaurantAgent + LodgingAgent run concurrently

### query_poi_context test coverage (deferred)

No dedicated test file exists yet. To add:
- Mock `POIChunker.chunk_and_index` and `KnowledgeRAG.query`
- Test empty-description path returns the fallback string
- Test graceful handling of malformed `rated_pois_json`
- Follow `patch.object(sys.modules["routeiq.agent.tools.query_poi_context"], ...)` pattern (see architecture decisions memory — required for `@tool`-decorated modules)

---

## Key files touched this session

| File | Change |
|------|--------|
| `routeiq/agent/tools/query_poi_context.py` | NEW — Vector RAG + KG enrichment tool |
| `routeiq/agent/tools/__init__.py` | Added `query_poi_context` to `ALL_TOOLS` |
| `routeiq/agent/day_trip_agent.py` | Added `"query_poi_context": "rag"` to `_TOOL_TO_STEP` |
| `routeiq/insights/prompts/day_trip_planner.py` | V3 prompt — step 3, updated `why_visit` instruction |
| `routeiq/ratings/factory.py` | Default `"foursquare"` → `"llm_synthetic"` |
| `tests/ratings/test_factory.py` | Updated test to assert `LLMSyntheticRatingProvider` as default |
| `README.md` | Full overhaul — RAG layers, module layout, corrected env vars, design patterns |
| `docs/presentation-framework.html` | NEW — group presentation doc |
