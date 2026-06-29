# Handoff — Session 49

**Date:** 2026-06-28
**Branch:** main
**Status:** Session 48 changes committed and pushed. Two Week 5 plans written. Architecture docs updated. Ready to start building.

---

## What was done this session

### 1. Session 48 changes committed and pushed ✅

Committed and pushed the two-layer POI rating cache (poi_rating_store.py, rate_pois rewrite,
agent_state.py, day_trip_agent.py, llm_synthetic.py, tests). Also pushed ChromaDB cache files.
All 312 tests passing on main.

### 2. max_iterations reduced from 12 → 6 ✅

`day_trip_agent.py:381` — ReAct loop now caps at 6. Observed that real runs take ~3 iterations:
iter=0 select_pois_for_day, iter=1 rate_pois, iter=2 query_poi_context → STOP. 12 was headroom
from before tool calls were optimized. 6 is still safe headroom without wasting tokens on runaway loops.

### 3. Architecture + data-flows docs updated ✅

`docs/DayTripPlanner/architecture.md` and `docs/DayTripPlanner/data-flows.md` updated to reflect:
- Two-layer poi_cache pattern (Layer 1 state dict, Layer 2 ChromaDB poi_ratings)
- RunnableConfig injection pattern for @tool functions
- Timing table and API budget table
- Cache strategy summary table in data-flows.md

### 4. Week 5 — 9 activity tags finalized ✅

Extended from the session 48 draft (7 labels) to 9 agreed tags:

| Tag | What it covers |
|---|---|
| `hiking` | trails, peaks, waterfalls, nature walks, nature reserves |
| `biking` | cycling paths, bike routes, mountain biking |
| `swimming` | beaches (for swimming), pools, snorkeling |
| `kayaking` | kayaking, paddleboarding, canoeing, water sports |
| `kids` | playgrounds, zoos, theme parks (Disney, LEGOLAND, Six Flags), family |
| `picnic` | picnic areas, gardens, parks for relaxing |
| `history` | missions, historic sites, battlefields, museums, cultural landmarks — **NEW** |
| `food` | wineries, breweries, food markets, farm stands, tasting rooms — **NEW** |
| `scenic` | overlooks, viewpoints, coastal vistas, scenic drives — **NEW** |

Theme parks (Disney, LEGOLAND, Universal) → `kids`. OSM `tourism=theme_park` already maps there.

### 5. semantic_queries field designed ✅

Classifier outputs a per-slot semantic search string alongside `activities`:

```json
{
  "activities": ["hiking", "kids"],
  "semantic_queries": {
    "hiking": "waterfall trail scenic",
    "kids": "theme park family rides"
  },
  "user_context": "waterfall scenic outdoor family"
}
```

Decision: **separate field in DayTripState** (not packed into user_context) so `query_poi_context`
can index it independently. `user_context` remains a human-readable summary for the LLM prompt;
`semantic_queries` is a machine-readable dict for vector search.

`semantic_queries: dict` field is NOT yet added to `routeiq/agent/agent_state.py` — marked as
build step 1 in plan B.

### 6. Plan A — Unified POI Knowledge Base written ✅

[`docs/DayTripPlanner/plan-unified-poi-knowledge.md`](plan-unified-poi-knowledge.md)

Single ChromaDB `poi_knowledge` collection replacing both existing collections:
- `ead198e6…` (Wikipedia-only embeddings)
- `82708677…` (poi_ratings from session 48)

Coverage cascade per POI at prefetch time: Wikipedia → TripAdvisor → Tavily → LLM synthetic.
`rate_pois` becomes a fast metadata lookup (<0.5s); `query_poi_context` gets cross-source
semantic search (Tavily highlights, TripAdvisor snippets all embedded alongside Wikipedia).

**Plan A is Week 5 stretch goal.** Plan B (fine-tuned classifier) is the primary deliverable.
`semantic_queries` from Plan B plugs into Plan A's `POIKnowledgeStore.query()` when Plan A is built.

### 7. Plan B — Fine-Tuned Intent Classifier refined ✅

[`docs/DayTripPlanner/plan-week5-finetuned-intent-classifier.md`](plan-week5-finetuned-intent-classifier.md)

Updated from session 48 draft:
- 9 tags (was 7)
- `semantic_queries` output added (was just `activities + user_context`)
- 21-query golden eval set across 3 tiers (Tier 2 = semantic gap = the submission story)
- Training data: 1000 ShareGPT examples (100/tag single-label + 70 multi-label + 30 none)
- `QueryIntentClassifier` class spec — NOT an `ActivityClassifier` subclass

Semantic gap examples table (the "why labels matter" story for the submission doc):

| Query | Keyword bag? | Tag needed |
|---|---|---|
| "somewhere with a waterfall" | ❌ | `hiking` |
| "wine country tour" | ❌ | `food` |
| "rollercoasters and theme parks" | ❌ | `kids` |
| "historic old town, missions" | ❌ | `history` |
| "great ocean views" | ❌ | `scenic` |
| "paddleboard or snorkel" | ❌ | `kayaking` + `swimming` |

### 8. Training platform evaluation 🔲

User has:
- **Fireworks AI** credits (A100s available, cloud fine-tuning)
- **Apple M3 Max, 64GB unified memory** — PyTorch NOT YET INSTALLED

**Decision point entered but not resolved:** check Fireworks AI first for Qwen3-1.7B support,
then fall back to M3 Max local if Fireworks doesn't support it.

Fireworks key questions: (a) Qwen3-1.7B in supported base model list? (b) Dataset format — ShareGPT accepted? (c) Credit cost per fine-tuning run?

M3 Max setup if needed:
```bash
pip install torch torchvision torchaudio          # PyTorch with MPS
pip install "llamafactory[torch,bitsandbytes]"    # LLaMA-Factory
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0       # use full 64GB
```

---

## Current state

| Item | State |
|---|---|
| Branch | main |
| Tests | 312/312 passing |
| Git | All session 48 + 49 docs committed and pushed |
| `poi_rating_store.py` | In prod — ChromaDB poi_ratings collection active |
| `max_iterations` | 6 (day_trip_agent.py:381) |
| `plan-week5-finetuned-intent-classifier.md` | Complete — 9 tags, semantic_queries, golden eval, training format |
| `plan-unified-poi-knowledge.md` | Complete — stretch goal for Week 5 |
| `architecture.md` / `data-flows.md` | Updated to reflect session 48+49 changes |

---

## What's next — build order for Week 5 (deadline July 2, 11pm PST)

### Immediate (next session start)

1. **Check Fireworks AI** — can it fine-tune Qwen3-1.7B? What format? What does a run cost?
   - If yes: upload training data, start run, screenshot
   - If no: install PyTorch MPS on M3 Max, run LLaMA-Factory locally

### Build order (after training platform chosen)

| Step | File | Notes |
|---|---|---|
| 1 | `routeiq/agent/agent_state.py` | Add `semantic_queries: dict = {}` field |
| 2 | `eval/intent_eval_golden.py` | 21 golden queries; run against keyword bag baseline first |
| 3 | `scripts/generate_intent_training_data.py` | 1000 ShareGPT examples via Claude Haiku API |
| 4 | `data/intent_train.json` + `data/intent_val.json` | Output of step 3 (80/20 split) |
| 5 | `notebooks/finetune_day_trip_intent.ipynb` | Adapt course notebook for 9-tag domain |
| 6 | Train on Fireworks OR M3 Max | Screenshots for submission |
| 7 | `routeiq/activities/finetuned_classifier.py` | `QueryIntentClassifier.classify(text)` |
| 8 | `routeiq/activities/factory.py` | Add `finetuned` branch |
| 9 | `app.py:672` | Replace `_infer_activities_from_text()` when `ACTIVITY_PROVIDER=finetuned` |
| 10 | `pytest tests/ -v` | Expect 312+ passed; default provider unchanged |

### Key wiring to remember

`_infer_activities_from_text()` is at `app.py:535` (function definition) and called at `app.py:672`.
Replace the call site with:
```python
if os.getenv("ACTIVITY_PROVIDER") == "finetuned":
    result = intent_classifier.classify(user_context_text)
    final_activities = result["activities"]
    semantic_queries = result["semantic_queries"]
else:
    final_activities = _explicit or _inferred
```

### Eval story for submission

- Baseline: keyword bag scores ~0% on Tier 2 (semantic gap queries)
- Fine-tuned: Tier 2 accuracy ≥ 80%
- Headline metric: **Tier 2 accuracy delta** = the submission story

---

## Files to read at new session start

- [`plan-week5-finetuned-intent-classifier.md`](plan-week5-finetuned-intent-classifier.md) — full build spec
- [`plan-unified-poi-knowledge.md`](plan-unified-poi-knowledge.md) — stretch goal (Plan A)
- `routeiq/agent/agent_state.py` — add `semantic_queries` field here first
- `app.py:535` and `app.py:672` — current keyword bag implementation to replace
