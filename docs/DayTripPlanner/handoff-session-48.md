# Handoff — Session 48

**Date:** 2026-06-27
**Branch:** main
**Status:** POI rating cache implemented and tested (312/312). Two Week 5 plans written. Not yet committed.

---

## What was done this session

### 1. Week 5 Project Handout analyzed ✅

Broke down the course deliverable: fine-tune Qwen3-1.7B-Base as a support ticket router using LLaMA Factory + LoRA on Google Colab (free T4). Pass/fail grading — submit screenshot of successful notebook run. Deadline July 2, 11pm PST.

**Two submission paths identified:**
- **Standard**: run provided notebook, screenshot, submit Google Doc
- **Custom**: build something original, submit GitHub link instead

**Decision**: go custom — tie fine-tuning to DayTripPlanner to add real value.

---

### 2. Two implementation plans written ✅

**[`docs/DayTripPlanner/plan-week5-finetuned-intent-classifier.md`](plan-week5-finetuned-intent-classifier.md)**

Fine-tune Qwen3-1.7B-Base to classify day trip user queries into 7 activity categories:
`Nature & Outdoors | History & Culture | Food & Wine | Adventure | Family Activities | Urban Exploration | Scenic Drive`

Hooks in before the ReAct loop — pre-populates `DayTripState.activities` and `DayTripState.user_context` so the orchestrating LLM doesn't spend iter=0/1 deriving intent. New file: `routeiq/activities/finetuned_classifier.py`. Training data generated synthetically (100 examples per label via Claude/GPT-4). Same LoRA workflow as the course notebook, different domain.

**[`docs/DayTripPlanner/plan-poi-rating-cache.md`](plan-poi-rating-cache.md)**

Two-layer cache for `rate_pois`:
- Layer 1: `DayTripState.poi_cache` (in-session, zero latency)
- Layer 2: ChromaDB `poi_ratings` collection (21-day TTL, cross-session)

Provider-agnostic — works for llm_synthetic, TripAdvisor, Foursquare, and Tavily identically. The plan also documents this as a **standing architectural pattern**: any external call with stable results (Wikipedia, activity classifiers, search APIs) should check `POIRatingStore` before hitting the network. Identified all current call sites and marked activity classifiers as the next extension.

---

### 3. POI rating cache implemented ✅

#### Timing context (before this session)

```
# First query
iter=0  llm_think=3.70s  find_city_pois=0.04s
iter=1  llm_think=3.70s  rate_pois=6.13s
                            ├ wikipedia=1.18s (9 POIs)
                            └ llm_synthetic=4.94s (1 batch LLM call for all POIs)
iter=2  llm_think=6.22s  query_poi_context=0.38s
iter=3  llm_think=10.89s → STOP   total=31.07s
```

#### How LLM synthetic ratings actually work

Common misconception: NOT one LLM call per POI. `LLMSyntheticRatingProvider._call_llm_single()` sends ALL POIs in a single batch request (up to 50 per call). The LLM generates plausible-but-fake ratings, review counts, snippets, and hours for all POIs in one response. Result cached 21 days in `./cache/ratings/llm_synthetic_{city}.json`.

#### Files changed

| File | Change |
|------|--------|
| `routeiq/rag/poi_rating_store.py` | **NEW** — ChromaDB 21-day POI rating cache. `get_batch(city, names)` → single `collection.get(ids=[...])` for all POIs. `put_batch(city, entries)` → single `collection.upsert(ids=[...])`. Serialises Python lists as JSON strings (ChromaDB metadata constraint). |
| `routeiq/rag/__init__.py` | Exported `POIRatingStore` |
| `routeiq/agent/agent_state.py` | Added `poi_cache: dict` to `DayTripState` |
| `routeiq/agent/tools/rate_pois.py` | Full rewrite — two-layer cache; `config: RunnableConfig` param (injected, not LLM-visible); Layer 1 from state dict, Layer 2 from `POIRatingStore`; batch ops only |
| `routeiq/agent/day_trip_agent.py` | `_execute_tool(tool_call, poi_cache)` passes cache via `RunnableConfig`; `_plan` initialises from state, returns updated cache |
| `routeiq/ratings/llm_synthetic.py` | Removed `_load_or_generate` file cache — now pure fetch-and-return; caching is `POIRatingStore`'s job |
| `app.py` | Added `"poi_cache": {}` to initial state construction |
| `tests/ratings/test_llm_synthetic.py` | Removed `TestCaching` class (file cache gone); added `test_always_calls_llm_no_internal_cache` to assert pure-fetch behaviour |

#### Bug found and fixed during implementation

First version looped 87 POIs and called `store.get()` / `store.put()` individually — 87+ sequential SQLite disk reads before the Wikipedia fetch even started. Discovered from timing log: `rate_pois wikipedia=14.60s pois=87` (up from 1.18s for 9 POIs). Fixed by replacing per-POI calls with single `get_batch` / `put_batch` calls.

#### Expected impact (production timing)

| Scenario | Before | After |
|---|---|---|
| First query, cold | rate_pois: 6.13s | ~6s (no change — all misses, 2 ChromaDB round-trips added) |
| Same-session refinement (same POIs) | rate_pois: ~2.5s | <0.1s (Layer 1 state hit) |
| App restart, same city | rate_pois: ~1.5s (LLM file cache only) | ~0.3s (ChromaDB batch hit) |
| Real provider (TripAdvisor/Tavily), 2nd call | rate_pois: full API cost again | ~0.3s (ChromaDB hit — 21 days) |

---

## Key architectural decisions made

### RunnableConfig injection pattern for stateful tools
`@tool` functions can declare `config: RunnableConfig` as the last parameter — LangChain injects it at `.invoke(args, config=...)` time and it does NOT appear in the tool's JSON schema exposed to the LLM. Used to pass `poi_cache` (mutable dict reference) into `rate_pois` without the LLM knowing about it.

```python
# In _execute_tool:
config = {"configurable": {"poi_cache": poi_cache}}
result = tool_map[name].invoke(args, config=config)

# In rate_pois:
session_cache: dict = (config.get("configurable") or {}).get("poi_cache", {})
```

Mutations to `session_cache` inside `rate_pois` propagate back to `poi_cache` in `_plan` (same dict object). `_plan` returns `{"poi_cache": poi_cache}` → persisted in LangGraph state via `MemorySaver`.

### `_keep` filter is provider-agnostic
Drops a POI only when rating < 3.8 AND review_count < 20 simultaneously. With `llm_synthetic` the LLM is constrained to 3.8–4.9 so this never fires. With real providers (TripAdvisor, Foursquare) where genuinely bad venues can surface from OSM, it prunes noise while keeping high-volume venues even if ratings are mixed.

### 21-day cache pattern (standing reference)
`POIRatingStore` is the canonical location for any "expensive external call with stable results." Future extension targets:
- `TavilyActivityClassifier` (web search per activity query)
- `PerplexityActivityClassifier` (API call per POI)
- Wikipedia thumbnail images (already has a file cache — could be unified into `poi_ratings` collection)

---

## What's not committed

All changes above are in the working tree but not yet committed. Run tests first:
```
python3 -m pytest tests/ -v   # expect 312 passed
```

---

## What's next

### Week 5 submission — Fine-tuned Intent Classifier

See full plan in [`plan-week5-finetuned-intent-classifier.md`](plan-week5-finetuned-intent-classifier.md).

Steps remaining:
1. Wait for the standard course notebook to arrive (provides training scaffold)
2. `scripts/generate_intent_training_data.py` — generate 700 synthetic examples (100 per label)
3. Register `day_trip_intent` dataset in LLaMA Factory
4. Train Qwen3-1.7B-Base via LLaMA Board on Colab T4 (LoRA rank 8, 3 epochs)
5. Merge adapter, smoke test 5 queries
6. Evaluate: precision/recall/F1 per label + confusion matrix + baseline vs fine-tuned delta
7. Wire `FineTunedIntentClassifier` into `routeiq/activities/factory.py`
8. Submit GitHub link (custom path, not Google Doc screenshot)

### query_poi_context test coverage (still deferred from session 47)

No dedicated test file exists. Pattern: mock `POIChunker.chunk_and_index` and `KnowledgeRAG.query`; test empty-description fallback; test malformed JSON handling.

---

## Current state

- **Branch:** main
- **Tests:** 312/312 passing
- **Git:** uncommitted changes (see `git diff --stat HEAD` for full list)
- **New ChromaDB collection:** `poi_ratings` — populated on next app run
- **Removed:** `./cache/ratings/llm_synthetic_{city}.json` file cache pattern (superseded by `poi_ratings` ChromaDB collection)
