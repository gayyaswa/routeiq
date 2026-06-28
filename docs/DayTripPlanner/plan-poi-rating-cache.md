# Plan: POI Rating Cache — LangGraph State + ChromaDB 21-Day Persistence

## Context

When a user refines a query ("remove trails, add kids activities"), the ReAct agent
re-calls `rate_pois` with an overlapping POI list. Tool calls jump 2 → 6 and total
time grows ~31s → ~44s. Two redundant costs hit for every already-seen POI:

1. **Wikipedia fetch** (~130ms per POI, parallel): re-fetches descriptions already
   retrieved in the first query turn.
2. **Rating provider call**: `LLMSyntheticRatingProvider` has a 21-day file cache
   but only for synthetic ratings. Real providers (TripAdvisor, Tavily, Foursquare)
   have **no cache** — every refinement turn pays full API cost again.

---

## How Rating Providers Work (Reference)

### Flow through `rate_pois`
```
find_city_pois → [N POIs from OSM graph]
    ↓
rate_pois(city, poi_list_json) called
    ↓
Wikipedia fetch — ThreadPoolExecutor, parallel
    For each POI without a description: WikipediaFetcher().enrich(poi)
    ~130ms per POI → 1.18s total for 9 POIs
    ↓
RatingsFactory.create() → active provider (env var RATING_PROVIDER)
    ↓
LLM synthetic (default):
    ONE batch LLM call for all POIs (up to 50 at once)
    Input:  [{name, category, subtype, description[:300]}, ...] for all POIs
    Output: [{name, rating, review_count, snippets, hours}, ...]
    Cost:   ~4.94s per batch, file-cached at ./cache/ratings/llm_synthetic_{city}.json

TripAdvisor: real API call per POI — paid, rate limited, no cache today
Foursquare:  real API call per POI — paid, rate limited, no cache today
Tavily:      web search + LLM per POI — ~1-3s per POI, no cache today
```

**Caching is more valuable with real providers** — real API calls are paid and
rate-limited. The file cache today only covers synthetic ratings.

---

## Architectural Pattern: 21-Day ChromaDB Cache

> **Internal Reference Checkpoint:** Any external call (Wikipedia, rating APIs,
> activity classifiers, search APIs) whose result is stable over days should use
> this pattern. Add ChromaDB as the persistence layer before reaching out to the
> network. Check here before adding new API calls anywhere in the codebase.

### Pattern

```
def get_or_fetch(key: str, fetch_fn, store: ChromaDB, ttl=21*86400):
    cached = store.get(key)
    if cached and time.time() - cached["cached_at"] < ttl:
        return cached
    result = fetch_fn()
    store.put(key, result)
    return result
```

### All call sites that benefit from this pattern

| Call site | File | Cost today | Cacheable? |
|---|---|---|---|
| Wikipedia descriptions | `rag/wikipedia_fetcher.py`, called from `rate_pois.py:63`, `day_trip_agent.py:320`, `tools/enrich_poi_details.py:28` | ~130ms/POI | Yes — text changes rarely |
| LLM synthetic ratings | `ratings/llm_synthetic.py` | ~5s/batch | Yes — file cache exists, move to ChromaDB |
| TripAdvisor ratings | `ratings/tripadvisor.py` | API call/POI, paid | Yes — ratings stable for weeks |
| Foursquare ratings | `ratings/foursquare.py` | API call/POI, paid | Yes — ratings stable for weeks |
| Tavily enrichment | `ratings/tavily_enrichment.py` | search+LLM/POI, ~2-3s | Yes — results stable for weeks |
| Tavily activity classifier | `activities/tavily_classifier.py` | search per activity query | Yes — POI×activity label stable |
| Perplexity activity classifier | `activities/perplexity_classifier.py` | API call per POI | Yes — POI×activity label stable |

**Not cacheable:** LLM narrative generation (per-itinerary), OSM graph queries (already cached by OSMnx).

---

## Two-Layer Cache Design

```
rate_pois called with N POIs
    ↓
Layer 1: LangGraph State  (in-session, zero latency)
    DayTripState.poi_cache["city||poi_name"] → hit? return immediately
    ↓ miss
Layer 2: ChromaDB         (cross-session, 21-day TTL)
    poi_ratings collection → hit within TTL? promote to Layer 1, return
    ↓ miss
Fetch: Wikipedia + rating provider → write to ChromaDB + Layer 1
```

---

## Files to Modify

### 1. `routeiq/agent/agent_state.py`

Add one field to `DayTripState`:
```python
poi_cache: dict[str, dict]   # "city||poi_name" → full rated POI dict; cleared on session reset
```
Initialize to `{}` when building the initial graph state.

### 2. `routeiq/rag/poi_rating_store.py` (NEW)

Provider-agnostic ChromaDB wrapper. Uses the existing ChromaDB client already
in the RAG layer — no new dependency.

```python
class POIRatingStore:
    """21-day ChromaDB cache for rated POI data — provider-agnostic (Registry pattern)."""

    _TTL = 21 * 86_400
    _COLLECTION = "poi_ratings"

    def __init__(self, chroma_client):
        self._col = chroma_client.get_or_create_collection(self._COLLECTION)

    def get(self, city: str, poi_name: str) -> dict | None:
        result = self._col.get(ids=[_key(city, poi_name)],
                               include=["metadatas", "documents"])
        if not result["ids"]:
            return None
        meta = result["metadatas"][0]
        if time.time() - meta.get("cached_at", 0) > self._TTL:
            self._col.delete(ids=[_key(city, poi_name)])
            return None
        entry = dict(meta)
        entry["description"] = result["documents"][0]  # Wikipedia text stored as doc
        return entry

    def put(self, city: str, poi_name: str, entry: dict) -> None:
        description = entry.pop("description", "") or ""
        self._col.upsert(
            ids=[_key(city, poi_name)],
            documents=[description],           # searchable text
            metadatas=[{**entry, "cached_at": int(time.time())}],
        )
        entry["description"] = description

def _key(city: str, poi_name: str) -> str:
    return f"{city.lower().replace(' ', '_')}||{poi_name}"
```

**ChromaDB schema:**
- `document` = Wikipedia description text (searchable; enables semantic queries later)
- `metadata` = rating, review_count, snippets, hours, composite_score, photo_urls, cached_at
- `id` = `"{safe_city}||{poi_name}"` — deterministic, exact-match lookup

### 3. `routeiq/agent/tools/rate_pois.py`

Split POI list into Layer 1 hits, Layer 2 hits, and misses. Only process misses
through Wikipedia + rating provider. Write results back to both layers.

Access LangGraph state via `RunnableConfig` injection (LangGraph ≥ 0.2):

```python
@tool
def rate_pois(city: str, poi_list_json: str, config: RunnableConfig) -> str:
    state = config.get("configurable", {}).get("state", {})
    session_cache: dict = state.get("poi_cache", {})
    chroma = POIRatingStore(get_chroma_client())

    raw = json.loads(poi_list_json)
    pois = [POI(...) for d in raw]

    hits, misses = [], []
    for poi, d in zip(pois, raw):
        key = f"{city}||{poi.name}"
        if key in session_cache:
            hits.append({**session_cache[key], **_activity_extras(d)})
        elif cached := chroma.get(city, poi.name):
            session_cache[key] = cached
            hits.append({**cached, **_activity_extras(d)})
        else:
            misses.append((poi, d))

    if misses:
        miss_pois = [p for p, _ in misses]
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(_wiki_enrich, miss_pois))

        rated = RatingsFactory.create().enrich_batch(city, miss_pois)
        for rp, (_, d) in zip(rated, misses):
            entry = _build_entry(rp)
            entry.update(_activity_extras(d))
            chroma.put(city, rp.poi.name, entry)
            session_cache[f"{city}||{rp.poi.name}"] = entry
            hits.append(entry)

    # Write updated session cache back via LangGraph Command
    return Command(
        update={"poi_cache": session_cache},
        goto=Send(...),   # continue normal ReAct flow
    )
```

State write-back: use `langgraph.types.Command(update={"poi_cache": ...})`.

### 4. `routeiq/ratings/llm_synthetic.py`

Deprecate the file-based cache (`_load_or_generate`) once `POIRatingStore` is
wired into `rate_pois`. Cache responsibility moves up to the tool layer.
The `LLMSyntheticRatingProvider` becomes a pure fetch-and-return with no caching.
Existing `./cache/ratings/` JSON files can be migrated or left to expire.

---

## Expected Impact

| Scenario | Before | After |
|---|---|---|
| First query, cold | rate_pois: 6.13s | 6.13s (all misses — no change) |
| Same query, same session | rate_pois: ~1.5s | <0.1s (Layer 1 hit) |
| App restart, same city/POIs | rate_pois: ~1.5s (file cache, LLM only) | ~0.3s (ChromaDB hit, no wiki + no LLM) |
| Refinement (9 old + 3 new POIs) | rate_pois: ~2.5s | ~0.8s (9 L1 hits + 3 misses) |
| TripAdvisor, any 2nd call within 21 days | ~8-15s | ~0.3s (ChromaDB hit) |
| Tavily, any 2nd call within 21 days | ~3-5s/POI | ~0.3s (ChromaDB hit) |

---

## Future: Extend This Pattern to Activity Classifiers

`TavilyActivityClassifier` and `PerplexityActivityClassifier` call external APIs
per (POI, activity) pair. Once `POIRatingStore` pattern is proven, apply the same
wrapper to those providers:
- Key: `"activity||{city}||{poi_name}||{activity_label}"`
- TTL: 21 days
- Store: same `poi_ratings` collection or a separate `activity_classifications` collection

---

## Verification

1. First query → `logs/timing.log` unchanged (`wikipedia=~1.2s`)
2. Same query, same session → `rate_pois` completes in <0.1s
3. Restart, same query → ~0.3s (ChromaDB hit, no Wikipedia call)
4. Refinement with 3 new POIs → only 3 POIs show Wikipedia + LLM timing in log
5. Set `RATING_PROVIDER=tavily_enrichment` → confirm ChromaDB cache still intercepts
6. Manually set `cached_at` to 22 days ago → confirm re-fetch triggers on next call
7. `pytest tests/ -v` → `rate_pois` output format tests pass unchanged
