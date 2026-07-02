# Plan B — Fine-Tuned Day Trip Intent Classifier (Week 5)

## Problem

Activity detection today is a 15-keyword substring bag (`_infer_activities_from_text`, app.py:535).
It fires only when exact words appear. Queries with natural language intent but no trigger word
return `activities = []` → `select_pois_for_day` never runs → itinerary is scenic-only.

| User says | Keyword match? | What they actually want |
|---|---|---|
| "somewhere with a waterfall" | ❌ "waterfall" not in list | `hiking` slot — trail to a waterfall |
| "my 6-year-old would love it" | ❌ no exact "kids/child" | `kids` slot — playground / zoo |
| "rollercoasters and theme parks" | ❌ "theme park" not in list | `kids` slot — Great America / LEGOLAND |
| "wine country tour" | ❌ nothing matches | `food` slot — wineries guaranteed |
| "historic old town, missions" | ❌ nothing matches | `history` slot — Mission Dolores |
| "somewhere with great ocean views" | ❌ nothing matches | `scenic` slot — overlooks / viewpoints |
| "paddleboard or snorkel" | ❌ not in keyword list | `kayaking` + `swimming` slots |
| "bouldering spot" | ❌ not in list | `hiking` slot |
| "little ones need entertainment" | ❌ "little ones" not in list | `kids` slot |
| "brewery and food market" | ❌ nothing matches | `food` slot |

**Without a label:** the slot doesn't exist. A winery might still appear as a scenic fill if its
scenic score is high enough — but it's never guaranteed. With a label, `select_pois_for_day`
reserves a dedicated slot regardless of scenic score.

---

## What the Classifier Does

**Input:** raw free-text from the "user context" field

**Output:** structured intent
```json
{
  "activities": ["hiking", "kids"],
  "semantic_queries": {
    "hiking": "waterfall scenic trail",
    "kids": "theme park family rides"
  },
  "user_context": "waterfall scenic outdoor family"
}
```

`activities` → which slots to guarantee in `select_pois_for_day`
`semantic_queries` → per-slot text fed to Plan A's `POIKnowledgeStore.query()` inside `query_poi_context`
`user_context` → full context string for `SemanticRanker` and the LLM prompt

---

## 12 Activity Tags (final label set)

Started as 9 tags; expanded to 12 mid-week to fix the OSM subtype matching gap:

| Tag | What it covers | Origin |
|---|---|---|
| `hiking` | trails, peaks, waterfalls, nature walks | original |
| `biking` | cycling paths, bike routes, mountain biking | original |
| `swimming` | beaches, pools, snorkeling | original |
| `kayaking` | kayaking, paddleboarding, canoeing, water sports | original |
| `kids` | playgrounds, zoos, theme parks (Disney, LEGOLAND, Six Flags) | original |
| `picnic` | picnic areas, gardens, parks for relaxing | original |
| `history` | missions, historic sites, battlefields, museums, cultural landmarks | added Week 5 |
| `food` | wineries, breweries, food markets, farm stands, tasting rooms | added Week 5 |
| `scenic` | overlooks, viewpoints, coastal vistas, scenic drives | added Week 5 |
| `landmarks` | iconic tourist attractions, famous bridges/towers, must-see sights | **added mid-week** |
| `nature` | nature reserves, national parks, forests, wildlife areas (not hiking-specific) | **added mid-week** |
| `arts` | galleries, theatres, arts centres, cultural venues | **added mid-week** |

**Why landmarks/nature/arts were added:** OSM subtype `attraction` (Golden Gate Bridge, Coit Tower,
Bay Bridge, Alcatraz) had no activity tag — those POIs fell through to a scenic fill heuristic
(n_slots=80). Adding `landmarks` as a direct tag gives them a Track 1 match. `nature_reserve`
(Muir Woods) was hijacking the `hiking` slot; adding `nature` lets it match both. `gallery` and
`theatre` subtypes were entirely unmatched before.

**OSM subtype → activity mapping expanded** (`routeiq/activities/osm_classifier.py`):
- Multi-activity values now supported: `nature_reserve → ["hiking", "nature"]`
- New mappings: `attraction → landmarks`, `landmark → landmarks`, `park → nature`,
  `waterfall → ["hiking", "nature"]`, `gallery → arts`, `theatre → arts`, `arts_centre → arts`
- `n_slots` (Track 2 scenic buffer): 80 → 15 (direct matching now covers most subtypes)

---

## Architecture

```
User types free-text in "user context" field
    │
    ▼  QueryIntentClassifier.classify(text)     ← NEW: local Qwen3-1.7B (<100ms)
    │
    │  {"activities": ["hiking"],
    │   "semantic_queries": {"hiking": "waterfall trail scenic"},
    │   "user_context": "waterfall scenic outdoor"}
    │
    ▼  replaces _infer_activities_from_text() at app.py:672
    │
    ▼  injected into initial_state before graph.stream()
    │
    ▼  ReAct loop
         iter=0: select_pois_for_day(activities=["hiking"])  ← slot guaranteed
         iter=1: rate_pois → metadata from POIKnowledgeStore (Plan A)
         iter=2: query_poi_context(semantic_queries={"hiking": "waterfall trail"})
                  → POIKnowledgeStore.query("waterfall trail")
                  → Lands End scores high (Tavily: "coastal trail, waterfall at low tide")
```

**`QueryIntentClassifier` is NOT an `ActivityClassifier` subclass.**
`ActivityClassifier.classify_batch(city, pois, activities)` classifies POIs.
`QueryIntentClassifier.classify(text)` classifies a user query. Different role, different class.

The existing OSM/Tavily `ActivityClassifier` still runs inside `select_pois_for_day` for POI matching.

**Dependency on Plan A:** `semantic_queries` only unlocks cross-source semantic search after
`POIKnowledgeStore` is implemented. Without Plan A, `semantic_queries` still improves
`SemanticRanker` (already consumes `user_context`) but not `query_poi_context`.

---

## Why labels matter — semantic gap examples for eval and documentation

### Without label → activities = [] → scenic fills only, no slot guaranteed
See the table in the Problem section above. Each query returns `activities = []` from the
keyword bag. The right POI may or may not appear as a scenic fill by luck.

### With fine-tuned label → correct tag → dedicated slot guaranteed
Same queries → correct activity tags → `select_pois_for_day` reserves the slot.

**The key word is "guaranteed."** "Wine country tour" to Sonoma with no label might return
zero wineries if their scenic scores are lower than Golden Gate Park. With `food` label it
gets a winery slot regardless.

**`semantic_queries` adds a second layer of precision:** the winery that gets selected is the
one most semantically similar to "winery vineyard wine tasting" across all provider content
in `POIKnowledgeStore` — not just the one with the highest generic scenic score.

---

## Eval golden set — `eval/intent_eval_golden.py`

Three tiers measure different dimensions. Run against both the keyword bag baseline and the
fine-tuned model; the delta is the submission story.

### Tier 1 — Easy (keyword bag handles these; both should pass)
```python
{"query": "I want to go hiking near the city",        "expected": ["hiking"]},
{"query": "planning a family picnic in the park",     "expected": ["picnic", "kids"]},
{"query": "find a good swimming beach",               "expected": ["swimming"]},
{"query": "bike trail along the coast",               "expected": ["biking"]},
{"query": "kayaking on the bay",                      "expected": ["kayaking"]},
```

### Tier 2 — Semantic gap (keyword bag fails; fine-tuned should pass)
```python
{"query": "somewhere with a waterfall",               "expected": ["hiking"]},
{"query": "my 6-year-old would love it",              "expected": ["kids"]},
{"query": "rollercoasters and theme parks",           "expected": ["kids"]},
{"query": "wine country tour",                        "expected": ["food"]},
{"query": "historic old town and missions",           "expected": ["history"]},
{"query": "somewhere with great ocean views",         "expected": ["scenic"]},
{"query": "paddleboard or snorkel spot",              "expected": ["kayaking", "swimming"]},
{"query": "bouldering spot near the city",            "expected": ["hiking"]},
{"query": "little ones need entertainment",           "expected": ["kids"]},
{"query": "brewery and food market district",         "expected": ["food"]},
```

### Tier 3 — Multi-label (measures upper bound; both may struggle)
```python
{"query": "scenic coastal hike with the kids",        "expected": ["hiking", "kids"]},
{"query": "wine tasting and a nice nature walk",      "expected": ["food", "hiking"]},
{"query": "historic brewery district tour",           "expected": ["history", "food"]},
{"query": "beach day with the family",                "expected": ["swimming", "kids"]},
{"query": "show me a nice day in SF",                 "expected": []},
{"query": "plan a relaxing afternoon",                "expected": []},
```

### Eval metrics per tier
- **Hit**: predicted set exactly matches expected (or is a superset with no wrong tags)
- **Partial**: at least one expected tag in predicted
- **Miss**: no overlap between predicted and expected
- Report: baseline vs fine-tuned accuracy per tier + overall delta
- Key story: Tier 2 baseline ≈ 0%, fine-tuned ≥ 80% → that's the submission delta

---

## Training data

**Format:** ShareGPT (mirrors course notebook exactly)
```json
{"conversations": [
  {"from": "system", "value": "You are a day trip intent classifier. Given a user query, output the activity tags that match their intent. Choose from: hiking, biking, swimming, kayaking, kids, picnic, history, food, scenic. Output matching tags as a comma-separated list, or 'none' if no activity is implied."},
  {"from": "human",  "value": "I want to find some waterfalls and do a hike with great views"},
  {"from": "gpt",    "value": "hiking, scenic"}
]}
```

**Volume:** ~1000 examples
- 100 per tag (single-label, clean signal) = 900
- ~70 multi-label (two-activity combinations) = ~70
- ~30 none cases (no activity) = 30

**Split:** 80/20 stratified → `data/intent_train.json` (800) + `data/intent_val.json` (200)

**Generation:** `scripts/generate_intent_training_data.py` — calls Claude API in batches,
generates diverse phrasings per tag (formal, casual, indirect, regional).

---

## Files to create / modify

| File | Change |
|---|---|
| `scripts/generate_intent_training_data.py` | **NEW** — 1000 ShareGPT examples via Claude API; writes train/val JSON |
| `data/intent_train.json` | 800 training examples (output of script) |
| `data/intent_val.json` | 200 validation examples (output of script) |
| `eval/intent_eval_golden.py` | **NEW** — 21 golden queries across 3 tiers; `run_intent_eval(classifier)` runs keyword bag + fine-tuned model, reports per-tier accuracy |
| `routeiq/activities/finetuned_classifier.py` | **NEW** — `QueryIntentClassifier`; loads merged Qwen3-1.7B; `classify(text)` → `IntentResult(activities, semantic_queries, user_context)` |
| `routeiq/activities/factory.py` | Add `finetuned` branch returning `QueryIntentClassifier` |
| `routeiq/agent/agent_state.py` | Add `semantic_queries: dict` field (set by classifier; empty dict = default) |
| `app.py` | Replace `_infer_activities_from_text()` at line 672 with classifier call when `ACTIVITY_PROVIDER=finetuned` |
| `notebooks/finetune_day_trip_intent.ipynb` | Course notebook adapted for 9-tag day-trip domain; upload to Colab, train, eval |

---

## Colab workflow (mirrors course notebook structure)

1. Upload `data/intent_train.json`, register in `dataset_info.json`
2. LLaMA Board: `Qwen/Qwen3-1.7B-Base` + `day_trip_intent` dataset + LoRA rank 8 + 3 epochs
3. Merge adapter → merged model weights
4. Baseline eval: zero-shot Qwen3-1.7B-Base on `intent_val.json`
5. Fine-tuned eval: merged model on `intent_val.json`
6. Metrics: per-tag precision/recall/F1, confusion matrix, baseline vs fine-tuned bar chart
7. Run `eval/intent_eval_golden.py` on both — Tier 2 delta is the headline result

---

## OSM classifier extension (one-line fix while we're here)

Add `waterway=waterfall` → `hiking` in `osm_classifier.py` so waterfall POIs get classified
as hiking-relevant in the existing OSM path too. Generalizes the pattern for any tag currently
missing from the lookup table.

---

## Build order

1. Update `routeiq/agent/agent_state.py` — add `semantic_queries` field
2. `eval/intent_eval_golden.py` — golden set + baseline run (measures current state)
3. `scripts/generate_intent_training_data.py` — generate 1000 examples
4. Adapt course notebook → `notebooks/finetune_day_trip_intent.ipynb`
5. Colab: train, merge, eval → screenshots for submission
6. `routeiq/activities/finetuned_classifier.py` + factory + app.py integration
7. `pytest tests/ -v` → 312+ passed (default `ACTIVITY_PROVIDER=osm` unchanged)
8. `osm_classifier.py` — add `waterway=waterfall → hiking` and similar missing tags

---

## Submission assets (Week 5, due July 2)

- `data/intent_train.json` + `data/intent_val.json`
- `scripts/generate_intent_training_data.py`
- `notebooks/finetune_day_trip_intent.ipynb` (Colab link)
- `eval/intent_eval_golden.py` + results (baseline vs fine-tuned, 3-tier)
- `routeiq/activities/finetuned_classifier.py` (integration code)
- Classification report screenshot + confusion matrix screenshot
- GitHub link (custom path — not the standard Google Doc screenshot)

---

## Verification

- `python eval/intent_eval_golden.py --baseline` → keyword bag accuracy (Tier 2 ≈ 0%)
- Colab: fine-tuned model → per-tag F1, confusion matrix, Tier 2 accuracy ≥ 80%
- `pytest tests/ -v` → 312+ passed
- `ACTIVITY_PROVIDER=finetuned FINETUNED_MODEL_PATH=./models/intent streamlit run app.py`
  → `logs/timing.log` shows `activities` pre-populated before iter=0
  → "somewhere with a waterfall" → `activities=["hiking"]`, `semantic_queries={"hiking": "waterfall trail"}`
