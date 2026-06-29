# Plan A — Unified POI Knowledge Base

## Problem

Two separate ChromaDB collections exist today and neither talks to the other:

| Collection | What it stores | Limitation |
|---|---|---|
| `poi_ratings` (session 48) | Structured ratings cache — rating, review_count, photos | No text embedding; can't be semantically searched |
| `ead198e6…` (week 3) | Wikipedia descriptions embedded for `query_poi_context` | Wikipedia only; misses TripAdvisor snippets, Tavily highlights |

Coverage gap: TripAdvisor `nearby_search` returns ~50 venues per city. The other 30–80 OSM POIs get no review data — they go through LLM synthetic but their text content is never embedded. A query for "waterfall trail" can't find "McWay Falls" if its Tavily description ("80-foot waterfall into the ocean") was never indexed.

Timing gap: data is fetched on-demand inside the ReAct loop. `rate_pois` triggers TripAdvisor calls at iter=1. `query_poi_context` triggers Wikipedia fetches at iter=2. First query for a new city is slow because all provider fetches happen serially inside tool calls.

---

## Solution — one unified `poi_knowledge` collection, prefetched at city load

### Unified ChromaDB document per POI

```
id:       "{city}:{poi_name}"
document: "{wikipedia_description}\n{tripadvisor_snippets}\n{tavily_highlights}"
           ↑ ALL text sources concatenated → single embedding vector
metadata: {
  "poi_name":        str,
  "city":            str,
  "rating":          float,       # 0–5; 0.0 if no provider data
  "review_count":    int,
  "photos":          str,         # JSON-encoded list of URLs
  "review_source":   str,         # "TripAdvisor" | "Tavily" | "llm_synthetic" | "none"
  "has_wikipedia":   str,         # "true" | "false"
  "has_provider":    str,         # "true" | "false"
  "activity_tags":   str,         # JSON-encoded list: ["hiking", "scenic"]
  "activity_evidence": str,       # JSON-encoded dict: {"hiking": "coastal trail, waterfall"}
  "timestamp":       int,         # epoch seconds — for TTL expiry
}
```

Single `collection.query(query_texts=["waterfall trail"])` returns semantic match score +
all structured metadata. No second lookup. Replaces both existing collections.

---

## Coverage cascade (prefetch order per POI)

```
For each POI in city at load time:
  1. Wikipedia description       → always fetched (stable, no TTL)
     → missing? → document = poi_name + category (minimal fallback)

  2. TripAdvisor nearby_search   → pool of ~50 venues (21-day cache per city)
     → POI matched? → add rating, review_count, snippets, photos
     → not matched (~60% of OSM POIs) → proceed to step 3

  3. Tavily enrichment search    → "{poi_name} {city} visitor highlights"
     → 1 call per unmatched POI (21-day cache per POI)
     → returns: rating_hint, highlights, visitor_quote
     → fills the gap for POIs TripAdvisor misses

  4. LLM synthetic               → only if steps 2+3 both miss
     → batch call for remaining unmatched POIs
     → always succeeds (no external dependency)

  All 4 sources → concatenate text → embed → upsert to poi_knowledge
```

Result: every OSM POI has at minimum a Wikipedia description embedded. ~90% have provider
data from TripAdvisor or Tavily. LLM synthetic fills the remainder.

---

## Prefetch trigger

In `app.py`, the city pre-flight already checks `kg.known_cities()` and fetches OSM POIs
if needed. Prefetch adds one step after:

```
1. kg.known_cities() check → OSM fetch if needed (existing)
2. POIKnowledgeStore.prefetch(city, kg.get_pois_for_city(city))   ← NEW
   → checks TTL per POI (21-day)
   → fetches only missing/expired POIs
   → shows st.spinner("Building POI knowledge base for {city}…") on cold start
   → instant on warm start (all hits)
3. Agent starts → all tool calls hit the knowledge store cache
```

Cold start (new city): ~30–120s depending on number of unmatched POIs and providers called.
Warm start (21 days): <1s (all ChromaDB hits).

---

## How `rate_pois` and `query_poi_context` change

### rate_pois (simplified)

```
Before: check poi_ratings (Layer 1 state, Layer 2 ChromaDB) → call provider → write to poi_ratings
After:  check poi_knowledge metadata → return structured fields directly (no provider call in loop)
        Provider calls happen at prefetch time, not inside the ReAct loop.
```

`rate_pois` becomes a fast metadata lookup — under 0.5s for any city that has been prefetched.
`poi_cache` in `DayTripState` (Layer 1 in-session dict) stays — still avoids repeated lookups
within the same session.

### query_poi_context (richer)

```
Before: fetch Wikipedia per POI → embed ephemeral ChromaDB → query by preferences list
After:  query poi_knowledge directly by semantic_queries dict values
        document already has Wikipedia + TripAdvisor + Tavily text embedded
        → cross-source semantic match: "waterfall trail" finds POI mentioned in Tavily
          even if Wikipedia doesn't mention waterfall
```

---

## Files to create / modify

| File | Change |
|---|---|
| `routeiq/rag/poi_knowledge_store.py` | **NEW** — unified ChromaDB store. `prefetch(city, pois)`, `query(city, text, n)`, `get_metadata(city, poi_names)`. Replaces `poi_rating_store.py`. |
| `routeiq/rag/__init__.py` | Export `POIKnowledgeStore`; deprecate `POIRatingStore` |
| `routeiq/rag/city_prefetcher.py` | **NEW** — orchestrates coverage cascade for a city; called from app.py pre-flight |
| `routeiq/agent/tools/rate_pois.py` | Rewrite: read from `poi_knowledge` metadata instead of calling providers; providers now called only in prefetch |
| `routeiq/agent/tools/query_poi_context.py` | Rewrite: query `poi_knowledge` with `semantic_queries` dict values instead of ephemeral ChromaDB |
| `app.py` | Add `city_prefetcher.prefetch()` call after OSM fetch pre-flight |
| `routeiq/agent/agent_state.py` | Add `semantic_queries: dict[str, str]` field (populated by Plan B classifier; empty dict = default) |
| `tests/rag/test_poi_knowledge_store.py` | **NEW** — unit tests for prefetch, TTL, cascade, query |

### Migration / retirement

- `routeiq/rag/poi_rating_store.py` → deprecated after Plan A; delete once `poi_knowledge` is stable
- ChromaDB collection `ead198e6…` (old Wikipedia-only) → no longer written to; can be deleted after migration
- ChromaDB collection `82708677…` (`poi_ratings`) → superseded by `poi_knowledge`

---

## Expected impact

| Scenario | Before Plan A | After Plan A |
|---|---|---|
| `rate_pois` first query, cold | ~6s (provider API calls in loop) | ~0.5s (prefetch done; metadata lookup only) |
| `rate_pois` warm | ~0.3s (ChromaDB batch) | ~0.1s (same, slightly faster — unified collection) |
| `query_poi_context` | Wikipedia only; ~0.4s fetch + embed | All sources pre-embedded; ~0.2s query |
| POI coverage (has review data) | ~40% (TripAdvisor pool match rate) | ~90% (TripAdvisor + Tavily cascade) |
| Cross-source semantic search | ❌ not possible | ✅ "waterfall" finds POI via Tavily snippet |

---

## Dependency

Plan B (fine-tuned classifier) outputs `semantic_queries: {"hiking": "waterfall trail"}`.
`query_poi_context` passes this to `POIKnowledgeStore.query(city, "waterfall trail")`.
The two plans combine: Plan A provides the rich index, Plan B provides the precise query.

---

## Verification

1. Run prefetch for SF → confirm all POIs have entries in `poi_knowledge`
2. Query `"waterfall trail"` → verify POIs with waterfall content rank above generic parks
3. `rate_pois` timing: confirm <0.5s after prefetch (no provider call inside ReAct loop)
4. POI with no TripAdvisor match → confirm Tavily fills the gap, LLM synthetic as final fallback
5. `pytest tests/ -v` → 312+ passed; new `test_poi_knowledge_store.py` passes
