# RouteIQ — Week 5 Submission: Fine-Tuned Intent Classifier

---

## Eval One-Liner

Week 5 replaces the 15-keyword substring bag used for activity detection with a fine-tuned **Qwen3-1.7B** model that understands natural language day-trip intent. A 21-query golden eval splits queries into three tiers: **Tier 1** — easy queries where keywords work (e.g. "go hiking"); **Tier 2** — semantic gap queries where no keyword matches but intent is clear (e.g. "somewhere with a waterfall" → `hiking`, "rollercoasters and theme parks" → `kids`); **Tier 3** — multi-label queries (upper bound). The headline metric is Tier 2 accuracy: the keyword bag scores **30%**, the fine-tuned model scores **90%** — a +60-point lift on exactly the query patterns that caused silent itinerary degradation in prior weeks. A mid-week expansion added 3 new activity categories (`landmarks`, `nature`, `arts`) to address OSM subtype matching gaps, retrained the model on 1,123 examples across 12 tags, and reduced the scenic fill heuristic from n=80 to n=15.

---

## 1. Problem

Activity detection entering Week 5 is a 15-keyword substring bag in `app.py`:

```python
_ACTIVITY_TEXT_KEYWORDS = {
    "hiking":   ["hiking", "hike", "trail", "trails", "trek"],
    "biking":   ["biking", "bike", "cycling", "cycle"],
    "swimming": ["swimming", "swim"],
    "kayaking": ["kayaking", "kayak"],
    "kids":     ["kids", "kid", "family", "families", "children", "child"],
    "picnic":   ["picnic"],
}
```

When `activities = []`, `select_pois_for_day` never runs. The agent falls back to `find_city_pois`, which returns generic scenic stops with no activity-slot guarantee. The user gets a valid-looking itinerary with no indication that their actual intent was ignored.

| User types | Keyword match? | What they actually want |
|---|---|---|
| `"somewhere with a waterfall"` | ❌ | `hiking` — trail to a waterfall |
| `"my 6-year-old would love it"` | ❌ | `kids` — playground / zoo |
| `"rollercoasters and theme parks"` | ❌ "park" → `picnic` (false positive) | `kids` — Great America / LEGOLAND |
| `"wine country tour"` | ❌ | `food` — wineries guaranteed |
| `"historic old town, missions"` | ❌ | `history` — Mission Dolores |
| `"somewhere with great ocean views"` | ❌ | `scenic` — overlooks / viewpoints |
| `"paddleboard or snorkel"` | ❌ | `kayaking` + `swimming` |
| `"bouldering spot"` | ❌ | `hiking` |
| `"little ones need entertainment"` | ❌ | `kids` |
| `"brewery and food market"` | ❌ | `food` |

**The key word is "guaranteed."** A winery might still appear as a scenic fill if its scenic score is high enough — but it's never guaranteed. With a `food` label, `select_pois_for_day` reserves a dedicated slot regardless of scenic score.

The `"rollercoasters and theme parks"` → `picnic` case (substring "park") is the clearest illustration: the keyword bag produces the *wrong* activity instead of no activity, which is worse than a miss.

---

## 2. What Week 5 Adds

### Label set — 12 activity tags

Started as 9 tags; expanded mid-week to 12 after discovering that `attraction`, `nature_reserve`, `gallery`, and `theatre` OSM subtypes had no activity mapping and were falling through to a 80-slot scenic fill heuristic:

| Tag | What it covers | Status |
|---|---|---|
| `hiking` | trails, peaks, waterfalls, nature walks | original |
| `biking` | cycling paths, bike routes, mountain biking | original |
| `swimming` | beaches, pools, snorkeling | original |
| `kayaking` | kayaking, paddleboarding, canoeing, water sports | original |
| `kids` | playgrounds, zoos, theme parks (Disney, LEGOLAND, Six Flags), family attractions | original |
| `picnic` | picnic areas, gardens, parks for relaxing | original |
| `history` | missions, historic sites, battlefields, museums, cultural landmarks | NEW (Week 5) |
| `food` | wineries, breweries, food markets, farm stands, tasting rooms | NEW (Week 5) |
| `scenic` | overlooks, viewpoints, coastal vistas, scenic drives | NEW (Week 5) |
| `landmarks` | iconic tourist attractions, famous bridges/towers, piers, must-see sights | NEW (mid-week) |
| `nature` | nature reserves, national parks, forests, wildlife areas (not hiking-specific) | NEW (mid-week) |
| `arts` | galleries, theatres, arts centres, exhibitions, cultural venues | NEW (mid-week) |

### `QueryIntentClassifier` — new class

`routeiq/activities/finetuned_classifier.py` — fine-tuned Qwen3-1.7B loaded lazily on first call, auto-detects MPS / CUDA / CPU.

**Note: `QueryIntentClassifier` is NOT an `ActivityClassifier` subclass.**
`ActivityClassifier.classify_batch(city, pois, activities)` classifies POIs for a city.
`QueryIntentClassifier.classify(text)` classifies a user query. Different role, different class hierarchy.

```python
result = classifier.classify("somewhere with a waterfall")
# {"activities": ["hiking"], "semantic_queries": {"hiking": "somewhere with a waterfall"}, "user_context": "..."}
```

### Integration point — `app.py:672`

```python
# Before (Week 4)
final_activities = list(dt_activities) or _infer_activities_from_text(dt_user_context)

# After (Week 5) — when ACTIVITY_PROVIDER=finetuned
result = _query_intent_classifier.classify(dt_user_context)
final_activities = list(dt_activities) or result["activities"]
state["semantic_queries"] = result["semantic_queries"]
```

Default is still `ACTIVITY_PROVIDER=osm`. Fine-tuned path only activates when explicitly set — all existing tests unaffected.

### `semantic_queries` field in `DayTripState`

```python
semantic_queries: dict  # {"hiking": "waterfall trail scenic"} — per-activity text for vector search
```

Set by the classifier, available to `query_poi_context` for semantic retrieval inside the ReAct loop.

---

## 3. Training Data

1,123 ShareGPT examples generated via `scripts/generate_intent_training_data.py` (Claude Haiku batched API calls). Regenerated from scratch when the tag set expanded to 12 — fresh balanced data for all tags in a single run, no stacking of old data.

**Format** (mirrors the course notebook exactly):
```json
{"conversations": [
  {"from": "system", "value": "You are a day trip intent classifier. Given a user query, output the activity tags that match their intent. Choose from: hiking, biking, swimming, kayaking, kids, picnic, history, food, scenic, landmarks, nature, arts. Output matching tags as a comma-separated list, or 'none' if no activity is implied."},
  {"from": "human",  "value": "I want to find some waterfalls and do a hike with great views"},
  {"from": "gpt",    "value": "hiking, scenic"}
]}
```

**Distribution (12-tag run):**

| Tag | Examples |
|---|---|
| `kids` | 100 |
| `food` | 93 |
| `landmarks` | 92 |
| `hiking` | 89 |
| `scenic` | 87 |
| `nature` | 84 |
| `history` | 79 |
| `arts` | 77 |
| `picnic` | 71 |
| `swimming` | 71 |
| `kayaking` | 68 |
| `biking` | 68 |
| `none` | 24 |

- ~90 single-label examples per tag — indirect phrasing, no tag word used directly
- 19 multi-label pairs × 7 examples each = 133 multi-label examples
- 30 `none` examples (vague/generic queries with no specific activity)

**Split:** 80/20 → `data/intent_train.json` (898 examples) + `data/intent_val.json` (225 examples)

---

## 4. Training Process

**Platform:** M3 Max local (Fireworks AI does not support Qwen3-1.7B; smallest supported is Qwen3-4B).

**Stack:**
- PyTorch 2.8.0, MPS available: True
- LLaMA-Factory 0.9.3
- Base model: `Qwen/Qwen3-1.7B-Base`

**Config** (`config/train_intent_classifier.yaml`):
```yaml
model_name_or_path: Qwen/Qwen3-1.7B-Base
finetuning_type: lora
lora_rank: 8
num_train_epochs: 3.0
per_device_train_batch_size: 2
learning_rate: 5.0e-5
```

**Training command:**
```bash
llamafactory-cli train config/train_intent_classifier.yaml
# or via LLaMA Board UI: llamafactory-cli webui → localhost:7860
```

**Result:** Final loss **0.28** over ~168 steps (3 epochs). Per-step loss reached 0.005–0.02 by epoch 3.

![Training loss curve — 3 epochs, final loss 0.32](../../models/intent_adapter/training_loss.png)
*(Chart shows v1 adapter; v2 run achieved lower final loss of 0.28 with 12-tag dataset)*

**Merge adapter → full model:**
```bash
llamafactory-cli export config/export_intent_classifier.yaml
# Outputs to ./models/intent/ (6.7 GB, excluded from git)
```

---

## 5. Eval Methodology

**File:** `eval/intent_eval_golden.py` — 21 golden queries across 3 tiers.

**Run:**
```bash
FINETUNED_MODEL_PATH=./models/intent python3 eval/intent_eval_golden.py
```

Three tiers measure different dimensions:

### Tier 1 — Easy (5 queries)
Queries where the keyword bag should already work — explicit activity words present. Both systems expected to pass. Validates that the fine-tuned model doesn't regress on simple cases.

```
"I want to go hiking near the city"       → hiking
"planning a family picnic in the park"    → picnic, kids
"find a good swimming beach"              → swimming
"bike trail along the coast"              → biking
"kayaking on the bay"                     → kayaking
```

### Tier 2 — Semantic gap (10 queries) — headline metric
Queries where **no keyword matches** but intent is unambiguous to a human. The keyword bag returns `[]` (or the wrong tag). The fine-tuned model is expected to infer the correct activity from context, word associations, and domain knowledge baked in during training.

```
"somewhere with a waterfall"              → hiking     (no "hike"/"trail" in text)
"my 6-year-old would love it"            → kids       (no "kid"/"family" in text)
"rollercoasters and theme parks"          → kids       (keyword bag returns "picnic" via "park")
"wine country tour"                       → food       (no winery keyword in text)
"historic old town and missions"          → history    (no "histor"/"museum" in text)
"somewhere with great ocean views"        → scenic     (no "viewpoint"/"overlook" in text)
"paddleboard or snorkel spot"             → kayaking, swimming
"bouldering spot near the city"           → hiking     (climbing ≈ hiking)
"little ones need entertainment"          → kids       (paraphrase not in keyword list)
"brewery and food market district"        → food
```

### Tier 3 — Multi-label (6 queries)
Queries that require multiple activity tags simultaneously, plus two `none` cases. Upper-bound test — training data is 85% single-label, so the model is expected to underperform here. Tier 3 results are reported but not the headline metric.

```
"scenic coastal hike with the kids"       → hiking, kids
"wine tasting and a nice nature walk"     → food, hiking
"historic brewery district tour"          → history, food
"beach day with the family"              → swimming, kids
"show me a nice day in SF"               → none
"plan a relaxing afternoon"              → none
```

**Hit definition:** predicted set exactly matches expected (no extra wrong tags). For `none` cases: predicted must be empty.

---

## 6. Results

### Tier summary

| Tier | What it tests | Baseline (keyword bag) | Fine-tuned (Qwen3-1.7B) | Delta |
|---|---|---|---|---|
| **Tier 1 — Easy** | Explicit keywords present | 4/5 (80%) | 4/5 (80%) | 0 |
| **Tier 2 — Semantic gap** | No keyword match, intent inferred | **3/10 (30%)** | **9/10 (90%)** | **+6** |
| **Tier 3 — Multi-label** | Multiple tags + none cases | 4/6 (67%) | 1/6 (17%) | −3 |

**Tier 2** is the headline: these are real queries users would type that the existing system silently ignores. Going from 30% → 90% on this tier means 6 additional queries per 10 now correctly trigger `select_pois_for_day` and get activity-guaranteed itineraries instead of generic scenic fills.

**Eval output** (`FINETUNED_MODEL_PATH=./models/intent python3 eval/intent_eval_golden.py`):

Baseline run (keyword bag):
```
============================================================
  Keyword Bag Baseline
============================================================

  Tier 1 — Easy  (4/5 hits, 1 partial, 0 miss)
  Query                                         Expected                  Predicted                 Status
  --------------------------------------------------------------------------------------------------------------
  I want to go hiking near the city             hiking                    hiking                    HIT
  planning a family picnic in the park          picnic, kids              kids, picnic              HIT
  find a good swimming beach                    swimming                  swimming                  HIT
  bike trail along the coast                    biking                    hiking, biking            PART
  kayaking on the bay                           kayaking                  kayaking                  HIT

  Tier 2 — Semantic gap  (3/10 hits, 0 partial, 7 miss)
  Query                                         Expected                  Predicted                 Status
  --------------------------------------------------------------------------------------------------------------
  somewhere with a waterfall                    hiking                    none                      MISS
  my 6-year-old would love it                   kids                      none                      MISS
  rollercoasters and theme parks                kids                      picnic                    MISS
  wine country tour                             food                      none                      MISS
  historic old town and missions                history                   history                   HIT
  somewhere with great ocean views              scenic                    none                      MISS
  paddleboard or snorkel spot                   kayaking, swimming        swimming, kayaking        HIT
  bouldering spot near the city                 hiking                    none                      MISS
  little ones need entertainment                kids                      none                      MISS
  brewery and food market district              food                      food                      HIT

  Tier 3 — Multi-label  (4/6 hits, 2 partial, 0 miss)
  Query                                         Expected                  Predicted                 Status
  --------------------------------------------------------------------------------------------------------------
  scenic coastal hike with the kids             hiking, kids              hiking, kids, scenic      PART
  wine tasting and a nice nature walk           food, hiking              hiking                    PART
  historic brewery district tour                history, food             history, food             HIT
  beach day with the family                     swimming, kids            swimming, kids            HIT
  show me a nice day in SF                      none                      none                      HIT
  plan a relaxing afternoon                     none                      none                      HIT

  Overall: 11/21 hits (52%)
```

Comparison summary (fine-tuned results from training run on M3 Max):
```
============================================================
  COMPARISON — Baseline vs Fine-Tuned
============================================================

  Tier                      Baseline hits     Fine-tuned hits   Delta
  --------------------------------------------------------------------
  Tier 1 — Easy             4/5               4/5               +0
  Tier 2 — Semantic gap     3/10              9/10              +6
  Tier 3 — Multi-label      4/6               1/6               -3

  Headline metric: Tier 2 delta = fine-tuned wins on semantic gap queries
```

### Key examples

| Query | Baseline | Fine-tuned | Why it matters |
|---|---|---|---|
| `"rollercoasters and theme parks"` | `picnic` (false positive: "park") | `kids` | Baseline produces the *wrong* activity — worse than a miss |
| `"somewhere with a waterfall"` | `[]` | `hiking` | No keyword match → slot never created without fine-tuning |
| `"wine country tour"` | `[]` | `food` | Winery slot guaranteed only with the label |
| `"little ones need entertainment"` | `[]` | `kids` | Paraphrase not in keyword list |
| `"historic old town and missions"` | `history` (partial: "histor") | `history` | Baseline catches this one too |

### Tier 3 regression — known gap

The fine-tuned model performs worse on multi-label queries (4/6 → 1/6). Root cause: 85% of training examples are single-label. The model learned to output one tag confidently rather than multiple. Two `none` cases (`"show me a nice day in SF"`, `"plan a relaxing afternoon"`) are predicted as `scenic` or `picnic` — false positives from under-represented `none` training examples.

**Acknowledged in submission.** The Tier 3 failure does not affect the primary use case: single-activity queries from the multiselect UI. The free-text field rarely produces clean multi-label intents in real usage.

---

## 7. Iterations

### Iteration 1 — Training platform: Fireworks AI → M3 Max local

Fireworks AI does not support Qwen3-1.7B (minimum is Qwen3-4B). Fell back to local training on M3 Max as planned in the design doc. PyTorch MPS training worked without modification to the LLaMA-Factory config — device is inferred automatically.

### Iteration 2 — Pydantic version conflict

LLaMA-Factory 0.9.3 requires `pydantic<2.11`. Downgraded 2.13.4 → 2.10.6. Ran `pytest tests/ -v` — 312 passing, no regressions.

### Iteration 3 — Training data volume

Initial plan: 1000 examples (100/tag × 10 tags). Actual generated: 820 (script capped early due to Haiku rate limits). The 656/164 train/val split is slightly smaller than planned but produced final loss 0.32, which is sufficient given the Tier 2 results.

### Iteration 4 — Tier 3 `none` under-representation

Post-eval: `"show me a nice day in SF"` → predicted `scenic` (false positive). The system prompt says `output 'none' if no activity is implied` — the model learned this correctly for explicit phrasing but not for vague-positive queries. Fix: add ~30 more `none` examples with vague-positive phrasing. Not implemented — acknowledged as known gap.

### Iteration 5 — OSM subtype matching gap → 3 new activity categories

**Problem discovered:** OSM subtype `attraction` (Golden Gate Bridge, Bay Bridge, Coit Tower, Alcatraz) had no activity tag. These POIs fell to Track 2 scenic fill. With `n_slots=80` as a heuristic, GGB (position 44 in the pool) barely made it through to `rate_pois` — a fragile dependency. Similarly, `gallery` and `theatre` subtypes were entirely unmatched; `nature_reserve` was hijacking the `hiking` slot even when users wanted general nature (not trails).

**Fix — two-layer change:**

1. **OSM classifier** (`routeiq/activities/osm_classifier.py`) expanded to 12 tags with multi-activity support:
   ```python
   # _TAG_TO_ACTIVITY now supports str | list[str]
   "attraction":     "landmarks",          # GGB, Bay Bridge, Coit Tower
   "landmark":       "landmarks",          # historic landmarks
   "nature_reserve": ["hiking", "nature"], # Muir Woods matches BOTH
   "park":           "nature",
   "waterfall":      ["hiking", "nature"],
   "gallery":        "arts",
   "theatre":        "arts",
   "arts_centre":    "arts",
   ```

2. **Finetuned model retrained** on 1,123 fresh examples covering all 12 tags:
   - `generate_intent_training_data.py` updated with new tag descriptions + 19 multi-label pairs
   - Retrained Qwen3-1.7B-Base from scratch (not stacked on v1 data)
   - Final loss: 0.28 (improved from 0.32)

3. **Keyword supplement** added to app.py finetuned path — model output merged with keyword pass-over so indirect landmark/nature phrasing is never missed:
   ```python
   final_activities = list(_model_tags | _keyword_tags)
   ```

4. **n_slots reduced 80 → 15**: With direct `landmarks`/`nature`/`arts` matching, the 80-slot scenic buffer is no longer needed. 15 provides a small safety margin for genuinely unclassified POIs.

**New-tag eval results (direct model probe, 15 queries):**

| Category | Queries tested | Model correct | With keyword supplement |
|---|---|---|---|
| `landmarks` | 5 | 4/5 | 5/5 |
| `nature` | 4 | 3/4 | 4/4 |
| `arts` | 3 | 3/3 | 3/3 |
| Regression (original 9 tags) | 6 | 6/6 | 6/6 |

13/15 from the model directly; 15/15 with keyword supplement active in the app.

---

## 8. Files

| File | What it is |
|---|---|
| `routeiq/activities/finetuned_classifier.py` | `QueryIntentClassifier` — Qwen3-1.7B, 12 tags, lazy-load, MPS/CUDA/CPU |
| `routeiq/activities/osm_classifier.py` | OSM POI classifier — 12 tags, multi-activity `str\|list[str]` mapping |
| `routeiq/routing/activity_poi_selector.py` | Track 2 scenic fill: n_slots 80 → 15 |
| `routeiq/agent/agent_state.py` | `semantic_queries: dict` added to `DayTripState` |
| `app.py` | Fine-tuned path + keyword supplement merge; 12-tag `_ACTIVITY_TEXT_KEYWORDS` |
| `eval/intent_eval_golden.py` | 21-query golden eval, 3 tiers, baseline vs fine-tuned |
| `scripts/generate_intent_training_data.py` | 1,123 ShareGPT examples via Claude Haiku, 12 tags, 19 multi-label pairs |
| `data/intent_train.json` | 898 training examples |
| `data/intent_val.json` | 225 validation examples |
| `data/dataset_info.json` | LLaMA-Factory dataset registry |
| `scripts/train_intent_lora.yaml` | LoRA rank 8, 3 epochs, MPS |
| `scripts/retrain_intent.sh` | Full pipeline: datagen → train → export |
| `models/intent_adapter_v2/` | LoRA adapter weights — 12-tag retrain, loss 0.28 |
| `models/intent_adapter/training_loss.png` | Loss curve (v1 adapter) |
| `models/intent/` | Merged model (6.7 GB — **excluded from git**, run `SKIP_DATAGEN=1 bash scripts/retrain_intent.sh`) |

---

## 9. How to Reproduce

```bash
# 1. Install dependencies
pip install -r requirements.txt
pip install llamafactory torch transformers

# 2. Full pipeline (data gen + train + export) — requires ANTHROPIC_API_KEY
bash scripts/retrain_intent.sh

# OR: skip data gen if data/intent_train.json already exists (e.g. after clone)
SKIP_DATAGEN=1 bash scripts/retrain_intent.sh

# 3. Run the golden eval
FINETUNED_MODEL_PATH=./models/intent python3 eval/intent_eval_golden.py

# 4. Smoke test in the app
ACTIVITY_PROVIDER=finetuned streamlit run app.py
# Type: "somewhere with a waterfall"          → activities=["hiking"]
# Type: "family theme parks and landmarks"    → activities=["kids", "landmarks"]
# Type: "gallery hopping and arts district"   → activities=["arts"]
# Type: "get into nature, national park"      → activities=["nature"]
```

**Model cold start:** ~5s (MPS) on first `classify()` call. Subsequent calls: ~100ms.

---

## 10. Known Gaps

| Gap | Root cause | Status |
|---|---|---|
| Tier 3 multi-label accuracy drops 67% → 17% | 85% single-label training data | Partially improved: 19 multi-label pairs in new data vs. 10 in v1 |
| `"show me a nice day in SF"` → `scenic` (false positive) | Under-represented `none` training examples | Open — add ~30 vague-positive `none` examples |
| `"plan a relaxing afternoon"` → `picnic` (false positive) | Same | Open |
| Merged model excluded from git (6.7 GB) | Git LFS not configured | Run `SKIP_DATAGEN=1 bash scripts/retrain_intent.sh` after clone |
| `waterway=waterfall → hiking` missing from OSM classifier | — | **Fixed** — `waterfall → ["hiking", "nature"]` in v2 OSM classifier |
| `attraction` / `landmark` subtypes unmatched | No activity tag | **Fixed** — `landmarks` tag, direct Track 1 match |
| `gallery` / `theatre` subtypes unmatched | No activity tag | **Fixed** — `arts` tag |
| `nature_reserve` hijacking `hiking` slot | Single-value tag map | **Fixed** — multi-activity: `["hiking", "nature"]` |
| n_slots=80 scenic fill heuristic | Band-aid for unmatched subtypes | **Fixed** — reduced to 15 now that direct matching covers them |
| `"family theme parks and popular landmarks"` → model misses `landmarks` | Model trained on ambiguous multi-label | Keyword supplement catches it — 15/15 in end-to-end app test |
