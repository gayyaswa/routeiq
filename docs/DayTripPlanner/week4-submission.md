# RouteIQ — Week 4 Submission: Evaluation

---

## Eval One-Liner

The eval measures **tool routing accuracy**, **activity recall**, **plan time**, **enrichment quality** (% stops rated, % with reviews, % with photos, avg rating), and **activity match quality** (% of matched stops with a written explanation, LLM-as-judge score 1–5) on the RouteIQ Day Trip Planner using a golden dataset of 38 cases across San Francisco and New York City. Judge methods: code-based for routing, recall, and enrichment; LLM-as-judge for match quality (satisfies the "combine ≥2 judge types" requirement). Pass bar: 100% routing accuracy, ≥70% activity recall, p95 plan time under 90 seconds. Five configurations are compared across OSM vs Tavily activity classifiers and LLM-synthetic vs Tavily vs TripAdvisor rating providers.

---

## 1. Eval Framework

| Field | Detail |
|---|---|
| **Agent under test** | Day Trip Planner (Week 3 LangGraph ReAct agent) extended with activity-based POI selection (Week 4) |
| **User outcome** | User asks for a city day trip with specific activities (hiking, swimming, kids); agent selects POIs that actually support those activities — not just scenic POIs that happen to be nearby |
| **Metrics** | Tool routing accuracy (behavioral), activity recall (quality), activity coverage (quality), plan time p95 (latency) |
| **Judge method** | Code-based: tool routing = exact match on first POI tool name; activity recall/coverage = keyword match in stop text + `matched_activities` field from `select_pois_for_day` ToolMessage |
| **Golden dataset** | 38 hand-labeled cases: 30 activity-recall cases (15 happy path, 15 edge cases across San Francisco and New York City) + 8 tool-routing cases (4 with activities, 4 without, all Bay Area cities) |
| **Pass bar** | Routing: 8/8 (100%); Activity recall: ≥70% avg; Plan time: p95 < 90s |
| **Instrumentation** | `LANGCHAIN_PROJECT=routeiq-week4` — every agent run, tool call, and ToolMessage captured |
| **Baseline run** | Run 1: `ACTIVITY_PROVIDER=osm`, `RATING_PROVIDER=llm_synthetic` (30 queries) |
| **Failure analysis** | Dominant failure: activities present but wrong POI tool called (see Section 6) |
| **Improvements** | Activity-aware iter=0 nudge + auto-infer activities from user_context text (see Section 7) |
| **Post-improvement run** | Tool routing eval: 8 queries, ~5–10 min (see Section 8) |
| **What's next** | Enrich `select_pois_for_day` with Tavily web search for POIs without OSM activity tags; production monitoring on `routing_pass` |

---

## 2. What Week 4 Adds

Week 4 adds an **activity-based POI selection layer** on top of the Week 3 scenic agent. Instead of returning only scenic stops, the agent now classifies each POI for supported activities (hiking, biking, swimming, kayaking, kids, picnic) and applies a two-track merge:

- **Track 1 — activity slots**: POIs verified by the classifier to support the requested activity.
- **Track 2 — scenic fills**: Top remaining scenic POIs by score for slots not filled by activity matches.

The new `select_pois_for_day` tool replaces `find_city_pois` when activities are requested. Which tool gets called first is the key behavioral signal being evaluated.

| Component | Where |
|---|---|
| `OSMActivityClassifier` | Tag-based: matches hiking→peak/trail, kids→playground/zoo, swimming→beach/pool |
| `TavilyActivityClassifier` | Web-search based: classifies POIs whose OSM tags are ambiguous |
| `ActivityPOISelector` | Two-track merge: activity slots (Track 1) + scenic fills (Track 2) |
| `select_pois_for_day` tool | Agent calls this instead of `find_city_pois` when activities are non-empty |

---

## 3. The Four Metrics

### 3a. Tool Routing Accuracy (behavioral / trajectory)

**What it measures:** Whether the agent called the correct POI discovery tool first.

**Rule:**
- `activities` non-empty → first POI tool must be `select_pois_for_day`
- `activities` empty → first POI tool must be `find_city_pois`

**Why it matters:** If activities are set but `find_city_pois` is called, the activity classifier is never invoked. The user gets generic scenic POIs instead of activity-matched ones — the entire Week 4 feature is bypassed silently.

**Judge method:** Code-based, exact match. `score_tool_routing()` in `eval/evaluators.py` scans ToolMessages for the first call to either `select_pois_for_day` or `find_city_pois` and checks it matches the expected branch.

**Pass bar:** 8/8 (100%) on the tool routing golden dataset.

---

### 3b. Activity Recall

**What it measures:** Fraction of requested activities that appear in the itinerary.

**Judge method:** Code-based. First checks `matched_activities` field in the `select_pois_for_day` ToolMessage (ground truth from the classifier). Falls back to keyword search in stop text if `find_city_pois` was used instead.

**Pass bar:** ≥ `expected_min_recall` per query (0.5–1.0 depending on case difficulty).

---

### 3c. Activity Coverage

**What it measures:** Fraction of itinerary stops that mention at least one requested activity.

**Judge method:** Code-based keyword match against `ACTIVITY_KEYWORDS` dictionary per stop's name, description, category, and activities fields.

---

### 3d. Plan Time

**What it measures:** End-to-end agent run time from state init to draft itinerary.

**Pass bar:** p95 < 90s across all configurations.

---

## 4. Golden Datasets

### 4a. Activity Recall Dataset — 30 queries (`eval/langsmith_dataset.py`)

| Segment | Cases | What they test |
|---|---|---|
| Happy path | 15 | Single and multi-activity queries where OSM tags should match |
| Edge cases | 15 | Empty activities (scenic-only), unknown activity, budget caps, short trips |

All cases use **San Francisco, CA** (primary, 60+ POIs) and **New York, NY** (secondary, 200+ POIs) with `expected_min_recall` thresholds set per case based on OSM tag availability.

### 4b. Tool Routing Dataset — 8 queries (`eval/tool_routing_queries.py`)

| ID | City | Activities | Expected Tool | Notes |
|----|------|------------|---------------|-------|
| r1 | San Francisco, CA | hiking | `select_pois_for_day` | Exact user scenario that triggered the bug |
| r2 | San Francisco, CA | hiking, kids | `select_pois_for_day` | Multi-activity |
| r3 | Oakland, CA | biking | `select_pois_for_day` | Biking classification |
| r4 | San Jose, CA | kids | `select_pois_for_day` | Kids/family |
| r5 | San Francisco, CA | *(none)* | `find_city_pois` | Pure scenic |
| r6 | Oakland, CA | *(none)* | `find_city_pois` | user_context present, no activities |
| r7 | Berkeley, CA | *(none)* | `find_city_pois` | History/art preferences |
| r8 | San Jose, CA | *(none)* | `find_city_pois` | Architecture walk, no activity keywords |

All cities use the Bay Area KG master (pre-loaded, no Overpass fetch at eval time).

---

## 5. Eval Configurations (5-Run Comparison)

| Run | `ACTIVITY_PROVIDER` | `RATING_PROVIDER` | What it isolates |
|---|---|---|---|
| Run 1 — Baseline | `osm` | `llm_synthetic` | Tag-based activity + synthetic ratings |
| Run 2 — Classifier lift | `tavily` | `llm_synthetic` | Tavily activity inference vs OSM tags |
| Run 3 — Full Tavily | `tavily` | `tavily_enrichment` | Tavily activity + Tavily enriched ratings |
| Run 4 — OSM + TripAdvisor | `osm` | `tripadvisor` | Real ratings with OSM activity classifier |
| Run 5 — Tavily + TripAdvisor | `tavily` | `tripadvisor` | Best-of-all combination candidate |

Run 1 is the baseline. Runs 2–5 each isolate one variable: classifier quality (Runs 1→2), enrichment depth (Runs 2→3), and real vs synthetic ratings (Runs 1→4, 2→5).

Run with `--limit 3` for a quick sanity check (~15 agent calls, 15–30 min); omit for the full run (150 calls, ~5–8 hours):
```bash
python3 eval/run_week4_eval.py --limit 3   # quick
python3 eval/run_week4_eval.py             # full
```

Results → `eval/results_week4.md`.

---

## 6. Baseline Run & Failure Analysis

*3-case sanity run — `python3 eval/run_week4_eval.py --limit 3` — 2026-06-24. Q1–3 (SF hiking, biking, kids)*

### Sanity Run Results Across All 5 Configurations

| Metric | OSM+Synth | Tavily+Synth | Tavily+Enrich | OSM+TA | Tavily+TA |
|--------|-----------|--------------|---------------|--------|-----------|
| Pass rate | **3/3** | 2/3 | **3/3** | 1/3 | 2/3 |
| Routing accuracy | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Avg activity recall | **100%** | 67% | **100%** | 67% | 67% |
| Avg time (s) | 44.6 | 98.3 | 503.9 | 52.8 | 44.7 |
| % stops rated | 62% | 59% | 0% | 35% | 30% |
| % stops with reviews | 62% | 59% | 67% | 17% | 15% |
| % stops with photos | 0% | 0% | 0% | **35%** | **30%** |
| Avg rating | 4.43 | 4.30 | — | 4.47 | 4.50 |
| % matched with evidence | 0% | 33% | 33% | 0% | **67%** |
| Avg match quality (1–5) | — | 4.00 | 4.00 | — | 4.00 |

**Key signal:** Tool routing was perfect (3/3) in all 5 configurations — the activity-aware iter=0 nudge fix is holding. The biking case (Q2) fails recall in Runs 2, 4, and 5, which is the dominant gap going into the full 30-query run.

### Eval Iteration 1 — Findings and Next Steps

Running the 3-case sanity run surfaced two gaps that must be addressed before the full 30-query eval:

**Gap 1 — Biking 0% recall in Tavily and TripAdvisor configurations**

Q2 (SF biking) gets 100% recall in Run 1 (OSM+Synth) but 0% in Runs 2, 4, and 5. Tool routing still passes — `select_pois_for_day` is called correctly — but the downstream classifier fails to label any SF POI as matching "biking" when those providers are active.

Likely cause: Tavily web search for SF bike POIs returns venues (shops, cafes near the trail) rather than trail/path POIs that would match `OSMActivityClassifier` subtypes. TripAdvisor per-POI nearby-search logged 500 errors on Q2, meaning enrichment returned empty, which also breaks the recall path.

Fix priority: investigate whether the `biking` keyword list needs expansion and whether the Tavily classifier prompt handles infrastructure POIs (trails, greenways) differently from attraction POIs.

**Gap 2 — NYC LLM-synthetic ratings cache too thin**

`cache/ratings/llm_synthetic_new_york_ny.json` has 6 entries covering only: Stonewall Inn, Fraunces Tavern, Lower East Side Tenement Museum, South Street Seaport, Battery Harris East, and Central Park. SF has 80+ entries. When NYC queries (Q9–15) hit Runs 1 and 2, the rating provider will silently cache-miss on nearly every POI — not a recall failure, but enrichment metrics (%rated, %with reviews) will be misleadingly low.

Fix: seed NYC cache with ~50 entries covering the POIs the agent is likely to surface: Central Park, Brooklyn Bridge, AMNH, Prospect Park, Hudson River Park, Staten Island Greenbelt, Coney Island, Inwood Hill Park, etc.

**Steps taken to prepare for the full run:**

1. NYC wired into the knowledge graph (`knowledge_graph_data.py`) — 5 borough city nodes, 992 NYC POIs loaded from OSM bbox caches (pois_n40.813 and pois_n40.818), full RELATIONSHIPS and region hierarchy for `New York City` metro
2. `wikipedia_tag` filter removed; replaced with `name + category` gate — Bay Area pool grew from 95 to 984 POIs (10×); NYC adds another 992
3. Eval dataset rewritten from Texas to SF + NYC — 30 queries: Q1–8 SF happy-path, Q9–15 NYC happy-path, Q16–30 edge cases split across both cities

**Next before the full run:**
- [x] Fix biking 0% recall in Tavily/TA configs — resolved by Improvement 6 (Tavily cap removal) and Improvement 7 (OSM name matching); biking now 100% recall in all 5 configs
- [x] Seed NYC LLM-synthetic ratings cache — auto-seeded to 40 entries by Q9 on the `--limit 15` run
- [x] Run `--limit 15` to validate full happy-path block — see Eval Iteration 3 below

### Eval Iteration 2 — Root Cause Analysis (2026-06-24)

![Activity Pipeline — Bug Locations](./images/eval_activity_pipeline.png)

| # | Layer | Bug | Fix |
|---|-------|-----|-----|
| ① | KG loader | `subtype` dropped → tag lookup always fails | `"subtype": p.get("subtype")` in both loaders |
| ② | Tavily classifier | `poi_names[:40]` hides POI at index >40 | Remove cap — send all names |
| ③ | OSM classifier | Name search absent — trail names missed | Add name-based pass to `_match()` |
| ④ | POI selector | Fixed 1 slot regardless of 44 candidates | Scale: 1→1, 4→2, 11→3; proportional budget |
| ⑤ | LLM synthetic | 900-POI batch → context overflow | Chunk to batches of 50 |

**Verified after fixes:** SF OSM classifier finds 44 hiking, 7 swimming, 8 kids POIs (was 0 for all three). Expected Tavily biking recall to go from 0% → ≥50% once fix ② takes effect across full 30-query run.

### Dominant Failure Mode: Tool Routing Bug

**Discovery:** The failure surfaced when testing a San Francisco day trip with "scenic coastal hiking and family trails" — the plan returned only generic scenic POIs with no activity-matched stops and no Tavily enrichment.

**Root cause 1 — iter=0 nudge hardcoded `find_city_pois`** (`routeiq/agent/day_trip_agent.py`):

When the LLM skips all tool calls on the first ReAct iteration, the recovery nudge said:

```python
# Before fix — always sent LLM to find_city_pois
messages.append(HumanMessage(
    content="You must call find_city_pois first to discover POIs for this city. "
            "Please call the tools now — do not describe the plan, just call the tools."
))
```

With activities set (e.g. `["hiking", "kids"]`), this explicit mention of `find_city_pois` overrode the V2 prompt's instruction to call `select_pois_for_day`. The activity classifier was never invoked. The entire Week 4 feature was silently bypassed on any run where the LLM hesitated on the first iteration.

**Root cause 2 — `Activity style` text input did not feed `activities`** (`app.py`):

The UI has two separate controls: an `Activities` multiselect that populates `state["activities"]`, and an `Activity style` text input that populates `state["user_context"]`. The V2 prompt only routes to `select_pois_for_day` when `activities` is non-empty. Typing "scenic coastal hiking and family trails" in the text box while leaving the multiselect empty produces `activities=[]` — the scenic-only branch.

**Impact:** Any run where the LLM called no tools on iteration 0 (common on Nebius under load) silently degraded to scenic-only output with no error surfaced to the user.

---

### Eval Iteration 3 — Happy-Path Smoke Test: 15 Queries × 5 Configurations (2026-06-25)

`python3 eval/run_week4_eval.py --limit 15` — SF Q1–8 + NYC Q9–15 across all 5 configurations.

#### Full Comparison Table

| Metric | OSM+Synth | Tavily+Synth | Tavily+Enrich | OSM+TA | Tavily+TA |
|--------|-----------|--------------|---------------|--------|-----------|
| Pass rate | 13/15 | **15/15** | 14/15 | 13/15 | **15/15** |
| Routing accuracy | **15/15** | **15/15** | **15/15** | **15/15** | **15/15** |
| Avg recall | 83% | **100%** | 90% | 83% | 97% |
| Avg time (s) | 66.0 | 70.3 | **49.6** | **41.9** | 43.8 |
| % stops rated | 87% | 86% | 0% | 35% | 38% |
| % stops with reviews | 87% | 86% | **100%** | 23% | 25% |
| % stops with photos | 0% | 0% | 0% | **35%** | **38%** |
| Avg rating | 4.27 | 4.33 | — | 4.40 | **4.49** |
| % matched with evidence | 67% | 80% | **93%** | 67% | 80% |
| Avg match quality (1–5) | 3.72 | 3.64 | 3.73 | **3.74** | 3.62 |

**Routing accuracy: 15/15 (100%) in every configuration.** All 9 improvements are holding.

#### Key findings

**Classifier lift (Run 2 vs Run 1):** Tavily raises recall from 83% → 100% (+17%). The picnic gap (Q6 SF, Q13 NYC) that was 0% in Run 1 becomes 100% in Runs 2, 3, and 5 — Tavily web search correctly identifies parks as picnic destinations even without `leisure=picnic_site` OSM tags.

**Enrichment quality:** LLM-synthetic shows 87% rated vs TripAdvisor's 35% — but LLM ratings are fabricated and carry no real signal. TripAdvisor's 35% rating rate reflects real coverage: it finds ~1-in-3 OSM POIs in its database. The real advantage of TripAdvisor is photos (35–38% of stops get real photos vs 0% from LLM-synthetic).

**Best-of-all candidate:** Run 5 (Tavily + TripAdvisor) — 15/15 pass, 97% recall, 43.8s avg, 38% real photos, 4.49 avg rating.

**Recommended baseline:** Run 1 (OSM + LLM-Synthetic) when no API keys available — 13/15, 83% recall, zero external dependencies.

**Remaining failure:** Q6 SF picnic and Q13 NYC picnic (0% recall) in OSM configs (Runs 1 and 4). Root cause: `leisure=picnic_site` and `leisure=garden` are not fetched by the tourism/historic OSM loader. Fix: add these OSM categories to the POI fetcher.

---

## 7. Improvements and Measured Delta

### Improvement 1 — Activity-aware iter=0 nudge

**Lever:** Control flow — prompt engineering within the ReAct loop.

**Specific change** (`routeiq/agent/day_trip_agent.py`):

```python
# After fix — nudge is activity-aware
if activities:
    nudge = (
        f"You must call select_pois_for_day with "
        f"requested_activities={activities!r} to discover activity-matched POIs. "
        f"Do not call find_city_pois — select_pois_for_day handles both activity "
        f"matching and scenic fills. Please call the tools now."
    )
else:
    nudge = (
        "You must call find_city_pois first to discover POIs for this city. "
        "Please call the tools now — do not describe the plan, just call the tools."
    )
messages.append(HumanMessage(content=nudge))
```

**Failure cluster targeted:** Any run where `activities` is non-empty but the LLM skips tools on iteration 0.

**Predicted impact:** +100% tool routing accuracy for affected runs (was silently failing, now explicitly corrected).

---

### Improvement 2 — Auto-infer activities from user_context text

**Lever:** Input pre-processing — keyword extraction before state is built.

**Specific change** (`app.py`):

```python
_ACTIVITY_TEXT_KEYWORDS = {
    "hiking":   ["hiking", "hike", "trail", "trails", "trek"],
    "biking":   ["biking", "bike", "cycling", "cycle"],
    "swimming": ["swimming", "swim"],
    "kayaking": ["kayaking", "kayak"],
    "kids":     ["kids", "kid", "family", "families", "children", "child"],
    "picnic":   ["picnic"],
}

def _infer_activities_from_text(text: str) -> list[str]:
    low = text.lower()
    return [act for act, kws in _ACTIVITY_TEXT_KEYWORDS.items()
            if any(kw in low for kw in kws)]

# When building initial_state:
final_activities = list(dt_activities) or _infer_activities_from_text(dt_user_context)
```

A live caption under the text box shows detected tags: `Activity tags detected: hiking, kids`.

**Failure cluster targeted:** Users who type preferences in the free-text input but leave the multiselect empty.

**Predicted impact:** Eliminates the class of "user typed their intent correctly but UI routing sent them down the wrong branch" failures.

---

### Improvement 3 — Expanded POI pool: removing the wikipedia_tag filter

**Lever:** Data pipeline — knowledge graph loader.

**How it was found:**

The discovery happened while checking how many POIs each city had in the knowledge graph ahead of switching the eval dataset to San Francisco and New York. San Francisco returned 60 POIs. The raw cache file (`bay_area_all.json.gz`) had 984 POIs — only 6% were being loaded.

The cause was a filter in `knowledge_graph_data.py`:

```python
# Added when Wikipedia was the only enrichment source
if not p.get("wikipedia_tag"):
    continue
```

The reasoning made sense originally: Wikipedia enrichment needs a `wikipedia_tag` (e.g. `en:Golden Gate Bridge`) as the lookup key. A POI without one had no description and would produce an empty stop card. So anything without a tag was filtered out.

By Week 4, three new providers were wired in — TripAdvisor, Tavily, and LLM-synthetic. None of them need a `wikipedia_tag`. TripAdvisor looks up by name and coordinates. Tavily does a web search. The filter had become a legacy constraint silently discarding 94% of the available POI pool.

**The fix** (`routeiq/graph/knowledge_graph_data.py`):

```python
# Before — Wikipedia-only era
if not p.get("wikipedia_tag"):
    continue

# After — multi-provider era: name + category as the quality gate
if not p.get("name"):
    continue
if p.get("category") not in _VALID_CATEGORIES:
    continue
```

The name + category filter keeps junk out (benches, ATMs, unnamed map features) while letting TripAdvisor and Tavily act as the quality arbiters at runtime — which is the right place for that judgment.

**Why it matters for the eval:** Run 4 and Run 5 (TripAdvisor) are only meaningful if there are enough POIs in the pool for the rating provider to enrich. With 60 POIs in SF, many TripAdvisor lookups returned no data simply because the pool was too small. With the filter removed, the pool expands to hundreds of named, categorized POIs, making the enrichment comparison between Run 1 (LLM-synthetic) and Run 4/5 (TripAdvisor) a fair test.

---

---

### Improvement 4 — NYC city support wired into the knowledge graph

**Lever:** Data pipeline — new city loader + eval dataset pivot.

**Why it was needed:**

The original eval dataset used Texas cities (Austin, San Antonio, New Braunfels, Fredericksburg). The KG, OSM bbox POI caches, and ratings caches have no Texas data — the agent was being evaluated against cities it had no POIs for. This produced unreliable recall numbers that reflected missing data rather than classifier quality.

**The fix:**

NYC was wired into `knowledge_graph_data.py` as a peer metro region alongside Bay Area:

- 5 borough city nodes added (Manhattan, Brooklyn, Queens, Bronx, Staten Island) with centroids
- `_load_nyc_pois()` merges two OSM bbox cache files (`pois_n40.813` and `pois_n40.818`) — 992 POIs loaded after dedup
- `_NYC_CITY_REGIONS` + `_ALL_CITY_REGIONS` maps handle borough → sub-region and NYC metro umbrella edges in RELATIONSHIPS
- `POIS = _load_bay_area_pois() + _load_nyc_pois()` — total 1,976 POIs in the graph

The eval dataset was rewritten from 30 Texas queries to 30 SF + NYC queries, keeping the same structure (15 happy-path, 15 edge cases) but now targeting cities the system actually has data for.

Note: `get_pois_for_city()` uses OSM polygon geocoding (not centroids) for the actual agent lookup — so borough centroid accuracy is not critical for correctness; it only affects KG metadata labels.

**Why it matters for the eval:** The 5-configuration comparison is only interpretable when all configs draw from the same real POI pool. Texas queries with no cache data would have silently inflated fail rates in all configurations equally, masking the actual signal (which provider + classifier combination works best).

---

### Improvement 5 — Subtype passthrough in KG loaders

![Subtype passthrough before/after](./images/eval_subtype_fix.png)

**Problem:** `_load_bay_area_pois()` and `_load_nyc_pois()` omitted `"subtype"` from the POI dict, so every POI entered the classifier with `subtype=None` and tag lookups silently returned no match.

**Fix:** Added `"subtype": p.get("subtype")` to both loaders (`routeiq/graph/knowledge_graph_data.py`).

**Impact:** SF OSM hiking recall went from 0% → 100% on Q1 (hiking query); kids and swimming similarly unblocked.

---

### Improvement 6 — Tavily poi_names[:40] cap removed

![Tavily name cap before/after](./images/eval_tavily_name_cap.png)

**Problem:** `TavilyActivityClassifier._classify_pois()` sent only `poi_names[:40]` to the LLM — any POI at index >40 was never classified. Golden Gate Bridge (index ~420 in SF's 438-POI pool) was invisible to the biking classifier.

**Fix:** Removed the slice; also replaced manual `"```"` stripping with `re.sub` to handle varied fence formats (`routeiq/activities/tavily_classifier.py`).

**Impact:** Biking recall in Tavily configs expected to rise from 0% → ≥50% once full 30-query run completes.

---

### Improvement 7 — OSM classifier name-based keyword matching

**Problem:** `OSMActivityClassifier._match()` checked only OSM subtypes — trail names like "Coastal Trail" or "Bay Trail" have no `trail` subtype and were missed entirely.

**Fix:** Added a name-based keyword pass to `_match()` with equal priority to subtype matching (`routeiq/activities/osm_classifier.py`). A POI whose name contains `"trail"`, `"path"`, or `"greenway"` now matches hiking without requiring an exact subtype.

```python
# name-based pass (equal priority to subtype)
name_lower = (poi.name or "").lower()
for activity, patterns in _NAME_KEYWORDS.items():
    if activity in requested and any(p in name_lower for p in patterns):
        matched.add(activity)
```

**Impact:** Catches infrastructure POIs (trails, bike paths, swimming areas) whose OSM tagging uses free-form names rather than structured subtypes.

---

### Improvement 8 — Proportional slot scaling + LLM synthetic batch chunking

![Slot scaling before/after](./images/eval_slot_scaling.png)

**Problem A (slot scaling):** `ActivityPOISelector` always allocated `min(len(activities), 3)` total slots — hiking with 44 candidates and kids with 8 candidates each got exactly 1 slot regardless of candidate density. With `total_stops=5`, 3 slots were scenic fills even when activity candidates were plentiful.

**Fix A:** Two helpers in `routeiq/routing/activity_poi_selector.py`:
```python
def _slots_for_activity(candidates):
    n = len(candidates)
    return 3 if n >= 11 else (2 if n >= 4 else (1 if n else 0))

def _scale_slots_proportional(raw_slots, budget):
    # proportional distribution that guarantees ≥1 per activity
```
`select()` now pre-computes `candidates_by_activity`, derives per-activity weights, and passes `per_activity_slots` dict to `_build_track1()`, which takes `ranked[:n]` instead of `ranked[0]`.

**Impact A:** `activities=[hiking, kids], total_stops=5` → 2 hiking + 2 kids + 1 scenic (was: 1 hiking + 1 kids + 3 scenic).

**Problem B (LLM batching):** `LLMSyntheticRatingProvider._call_llm()` sent all city POIs in one call. For NYC (900+ POIs) this produced ~180K tokens of expected output, causing context overflow and returning `[]` — all NYC POIs got `rating=None`.

**Fix B:** `_call_llm` now chunks into batches of 50 (≈6K tokens each) and aggregates results; original call renamed `_call_llm_single` (`routeiq/ratings/llm_synthetic.py`).

**Impact B:** NYC enrichment goes from 0% rated → full coverage (~18 batches of 50); `llm_synthetic_new_york_ny.json` cache populates correctly on first run.

---

### Improvement 9 — Eliminate redundant ReAct tool calls (2026-06-24)

![ReAct loop before/after](./images/eval_react_loop_fix.png)

**Problem:** "Discovering city POIs" showed 28–38s across warm-cache runs even though Tavily and Wikipedia caches were fully populated. Per-tool timing instrumentation (`routeiq/timing.py`) revealed the root cause: the ReAct loop was making **12 tool calls per planning run and hitting the iteration cap** — meaning it never stopped on its own. Only 2 of the 12 calls did real work:

| Iteration | LLM think | Tool called | Tool elapsed | Useful? |
|-----------|-----------|-------------|-------------|---------|
| 0 | 2.3s | `select_pois_for_day` | 1.6s | ✅ finds POIs |
| 1 | 5.8s | `rate_pois` | 13.6s | ✅ rates + enriches |
| 2 | **7.5s** | `estimate_visit_duration` | 0.0s | ❌ data already in rate_pois |
| 3 | 2.2s | `estimate_visit_duration` | 0.0s | ❌ |
| 4 | 1.2s | `enrich_poi_details` | 0.0s | ❌ description already in rate_pois |
| 5–11 | 2–5s each | `estimate_visit_duration` / `enrich_poi_details` | 0–2.5s | ❌ |

The tools themselves cost nothing — `estimate_visit_duration` is a dict lookup (0.00s) and `enrich_poi_details` hits the Wikipedia cache. The cost is **LLM inference time per iteration**: the agent had to think for 1–8 seconds to decide to call each tool, adding ~35s of pure overhead for zero new information.

**Why the data was already there:** `rate_pois` internally calls `WikipediaFetcher.enrich()` for every POI before returning. The result is serialized via `dataclasses.asdict(poi)`, which includes `description` and `image_url`. The prompt didn't tell the LLM this, so it dutifully called `enrich_poi_details` separately for each stop anyway.

**Fix — two changes:**

1. **Pre-compute `visit_duration_min` in `rate_pois`** (`routeiq/agent/tools/rate_pois.py`): added a single dict lookup before returning each entry:
```python
entry["visit_duration_min"] = _VISIT_MINUTES.get((rp.poi.subtype or "").lower(), _DEFAULT_MINUTES)
```
The same `_VISIT_MINUTES` dict used by `estimate_visit_duration` — no new logic, just earlier placement.

2. **Update prompt to declare pre-populated fields** (`routeiq/insights/prompts/day_trip_planner.py`):
```
Tool call order:
1. select_pois_for_day (or find_city_pois)
2. rate_pois — returns description, image_url, AND visit_duration_min.
   Do NOT call enrich_poi_details or estimate_visit_duration — data is already present.
```

**Impact:** ReAct loop drops from 12 iterations (hit cap, never stopped) → 2–3 iterations (select → rate → output). "Discovering city POIs" step: **38s → ~5s**.

---

### Post-Improvement: Tool Routing Eval Results

Run the fast 8-query tool routing eval (~5–10 min) to verify both fixes:

```bash
python3 eval/run_tool_routing_eval.py
```

Results → `eval/results_tool_routing.md`.

**Result: 8/8 routing pass rate — target met.** *(run: 2026-06-24)*

| ID | City | Activities | Expected Tool | Actual Tool | Routing | Stops | Time |
|----|------|------------|---------------|-------------|---------|-------|------|
| r1 | San Francisco, CA | hiking | `select_pois_for_day` | `select_pois_for_day` | PASS | 9 | 35.8s |
| r2 | San Francisco, CA | hiking, kids | `select_pois_for_day` | `select_pois_for_day` | PASS | 7 | 61.5s |
| r3 | Oakland, CA | biking | `select_pois_for_day` | `select_pois_for_day` | PASS | 6 | 161.1s |
| r4 | San Jose, CA | kids | `select_pois_for_day` | `select_pois_for_day` | PASS | 4 | 84.4s |
| r5 | San Francisco, CA | — | `find_city_pois` | `find_city_pois` | PASS | 9 | 66.2s |
| r6 | Oakland, CA | — | `find_city_pois` | `find_city_pois` | PASS | 6 | 92.6s |
| r7 | Berkeley, CA | — | `find_city_pois` | `find_city_pois` | PASS | 5 | 262.2s |
| r8 | San Jose, CA | — | `find_city_pois` | `find_city_pois` | PASS | 4 | 152.9s |

**Target: 8/8 routing pass rate (100%).**

The tool routing eval also runs as part of the test suite via unit tests — 11 fast pytest cases with mocked ToolMessages (no API calls):

```bash
python3 -m pytest tests/test_tool_routing_eval.py -v
# 11 passed in 0.12s
```

---

## 8. Eval Instrumentation

| File | Purpose |
|---|---|
| `eval/langsmith_dataset.py` | 30 golden queries: `WEEK4_EVAL_QUERIES`, `ACTIVITY_KEYWORDS` dictionary |
| `eval/tool_routing_queries.py` | 8 tool routing golden cases: `TOOL_ROUTING_QUERIES` |
| `eval/evaluators.py` | `score_tool_routing()`, `score_activity_recall()`, `score_enrichment_quality()`, `score_activity_match_quality()`, `ActivityEvaluator` |
| `eval/run_week4_eval.py` | 5-configuration sweep (150 runs, `--limit N` for quick runs) → `eval/results_week4.md` |
| `eval/run_tool_routing_eval.py` | Fast routing check (8 runs) → `eval/results_tool_routing.md` |
| `tests/test_tool_routing_eval.py` | 11 unit tests for `score_tool_routing()` — no API calls, runs in 0.12s |

LangSmith project: `routeiq-week4`. Set via `LANGCHAIN_PROJECT=routeiq-week4` in `.env`.

---

## 9. LangSmith Observability & Performance Analysis

The Week 4 handout (Part 4) requires full end-to-end observability through LangSmith: every LLM call, every tool call, latency, and token cost visible before running any evals. This section documents the setup, what the traces revealed, and the performance improvements derived from them.

### 9a. Setup (7 steps from Part 4 playbook)

| Step | What was done |
|------|--------------|
| **1. Create project** | Project `routeiq-week4` created in LangSmith — all traces, datasets, and eval runs live there |
| **2. Enable tracing** | `.env` sets `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT=routeiq-week4`, `LANGCHAIN_ENDPOINT=https://api.smith.langchain.com` — LangGraph auto-instruments every LLM call and tool call |
| **3. Single run confirm** | Triggered a single SF hiking+kids run; confirmed in LangSmith UI: top-level agent run, every `select_pois_for_day` and `rate_pois` tool call, the LLM invocation inside `TavilyActivityClassifier._extract_matched_names`, per-call latency, and token counts |
| **4. Golden dataset** | 30 queries uploaded via `eval/langsmith_dataset.py` — each with city, activities, user_context, expected_min_recall, expected_tool |
| **5. Evaluators** | Code-based: `score_tool_routing()`, `score_activity_recall()`, `score_enrichment_quality()` in `eval/evaluators.py`; LLM-as-judge: `score_activity_match_quality()` — satisfies the "≥2 judge types" requirement |
| **6. Eval run** | `eval/run_week4_eval.py` runs 5 configurations × 30 queries = 150 LangSmith runs; `--limit 3` sanity run confirmed per-config traces visible |
| **7. Run comparison** | LangSmith Comparison view diffs baseline (OSM+Synth) vs. Tavily configurations per metric and per query |

### 9b. What the Traces Revealed

After the 3-case sanity run (2026-06-24), the per-step timing breakdown was added to the UI stepper (see Section 7, Improvement 8) to make trace data visible without opening LangSmith. The first full SF hiking+kids run showed:

| Step | Observed time | Root cause |
|------|--------------|-----------|
| Discovering POIs (`select_pois_for_day`) | ~40–60s | Tavily search cached (fast) but `_extract_matched_names` made **2 uncached LLM calls** — one per activity — each with ~984 POI names in the prompt |
| Rating stops (`rate_pois`) | ~180–210s | Wikipedia fetcher made **up to 3 HTTP requests per POI** (opensearch + summary + pageimages fallback) with no persistence — re-ran identically on every call including refinement. LLM synthetic batching also cold (20 batches × ~5s for first run) |
| Finalizing itinerary (`extract`) | ~15–20s | LLM narration — inherently latency-bound, no fix available |
| **Total** | **~266s** | |

LangSmith also surfaced a **timing accumulation bug**: the UI stepper showed only the last invocation's time when the ReAct loop called the same tool twice. The stepper showed `rate_pois: 5s` because the second (cached) call overwrote the first (slow) call's 180s.

### 9c. Performance Improvements

Three fixes derived directly from trace analysis:

**Fix A — Timing accumulation** (`routeiq/agent/day_trip_agent.py`)

`_emit_progress` used `step_times[current] = now - step_start` (overwrites). Changed to accumulate:
```python
step_times[current] = step_times.get(current, 0.0) + (now - step_start)
```
Now multi-iteration ReAct loops show total time across all invocations of a step. The stepper's live counter also ticks correctly through refinement iterations.

---

**Fix B — Cache Tavily LLM name extraction** (`routeiq/activities/tavily_classifier.py`)

**Problem:** Tavily web search results were cached for 21 days, but `_extract_matched_names` — which calls the LLM with all ~984 POI names to identify matches — ran on **every invocation**, uncached. Two LLM calls per run (one per activity for hiking+kids), each with a ~20K-token prompt.

**Fix:** Cache format changed from `[raw_results]` to `{"results": [...], "matched_names": [...]}`. On cache hit with `matched_names` already populated, the LLM call is skipped entirely:
```python
results, cached_names = self._fetch(city, activity)
if cached_names is not None:
    matched_names = cached_names          # 0 LLM calls
else:
    matched_names = self._extract_matched_names(results, poi_names, activity)
    self._save_matched_names(city, activity, matched_names)  # write-through
```
Old cache files (plain lists) are handled as legacy format — upgraded to new format on next run.

**Impact:** `select_pois_for_day` latency: ~50s (cold) → **<2s** (warm) for SF hiking+kids.

---

**Fix C — Wikipedia description cache** (`routeiq/rag/wikipedia_fetcher.py`)

**Problem:** `WikipediaFetcher.enrich()` made up to 3 HTTP round-trips per POI (opensearch → summary → pageimages) with `_REQUEST_TIMEOUT=15s`, but results were never persisted. Every `rate_pois` call — including every refinement — started fresh, repeating the same fetches.

**Fix:** Added a module-level write-through cache at `cache/wikipedia/descriptions.json` (same JSON-file pattern as `llm_synthetic.py` and `tavily_classifier.py` — see `TODO` in code for future unified `CacheLayer` refactor). Cache hits return immediately without any HTTP call; misses (including title-not-found) are also cached to avoid retries.
```python
hit = cache.get(poi.name)
if hit is not None:
    poi.description = hit.get("description") or poi.description
    poi.image_url   = hit.get("image_url")   or poi.image_url
    return           # 0 HTTP calls
```

**Impact:** `rate_pois` Wikipedia phase: ~30–40s (first run) → **<1s** (warm). Refinement no longer stalls — previously refinement re-ran all Wikipedia fetches and appeared stuck at "Rating stops"; now returns from cache instantly.

---

**Fix D — Eliminate redundant ReAct tool calls** (`routeiq/insights/prompts/day_trip_planner.py`, `routeiq/agent/tools/rate_pois.py`)

**Problem:** After caches warmed, "Discovering city POIs" still showed 28–38s. Added per-tool instrumentation (`routeiq/timing.py`) to log LLM think time and tool elapsed time per ReAct iteration. The log showed 12 iterations (hit the cap), with only 2 doing real work. The other 10 called `estimate_visit_duration` (0.00s each) and `enrich_poi_details` (0–2.5s each) — both redundant because `rate_pois` already returns `description`, `image_url`, and (after this fix) `visit_duration_min`. The wasted LLM inference overhead: ~35s.

**Fix:** `rate_pois` now pre-computes `visit_duration_min` per stop using the same `_VISIT_MINUTES` dict as `estimate_visit_duration`. Prompt updated to tell the LLM both fields are already present and to skip those two tools entirely.

**Impact:** ReAct loop 12 iterations → 2–3 iterations. "Discovering city POIs": **38s → ~5s** on warm runs.

### 9d. Post-Fix Latency (SF Swimming + Scenic Family Trails, warm caches)

Measured on second+ runs after activity caches are populated. All timings from live UI step breakdown.

| Fix applied | Discover POIs | Rate stops | Finalize | Total |
|-------------|--------------|------------|----------|-------|
| None (cold first run) | ~10s | ~200s | ~16s | **~226s** |
| After Fix A+B+C (caches warm, new activity first run) | ~12s | ~70s | ~14s | **~96s** |
| After Fix A+B+C (same activity, second run) | ~28–38s | **10s** | ~14–17s | **~52–65s** |
| After Fix D (prompt + rate_pois pre-compute) | **~5s** | ~10s | ~15s | **~30s** |

The remaining ~10s in "Rate stops" is Wikipedia parallel fetch for any POIs not yet in `cache/wikipedia/descriptions.json` — warms further as more activities are run. The ~15s finalize is LLM narration, which is inherently latency-bound and cannot be cached.

**Note on the 28–38s anomaly (pre-Fix D):** "Discovering city POIs" was getting *slower* across warm runs (28s → 38s) because the ReAct loop hit the 12-iteration cap on every run. The LLM always called `estimate_visit_duration` 7 times and `enrich_poi_details` 3 times, spending 2–8s of LLM inference per call. With non-deterministic LLM response times, the accumulated overhead varied per run.

### 9e. Production Monitoring (from Part 4 playbook)

| Signal | Alert condition | What it means |
|--------|----------------|---------------|
| `routing_pass < 1.0` | Any run with activities | iter=0 nudge regression |
| `activity_recall < 0.5` (50-run rolling avg) | Any config | OSM tag coverage drop or classifier prompt regression |
| `pct_rated < 0.5` on TripAdvisor runs | Any run | API quota or POI name-match failure |
| `plan_time_p95 > 90s` | Any config | Cache miss spike or new uncached API call introduced |
| `tavily_matched_names` cache miss rate > 0 on warm runs | Tavily configs | Cache write failure or cache cleared unexpectedly |
| Wikipedia cache miss rate > 5% on warm runs | All configs | New POIs outside cache coverage, or cache file corrupted |

---

## 10. What's Next

### Immediate (before full 30-query run)

1. **Fix biking 0% recall in Tavily/TA configs** — investigate whether the Tavily classifier prompt correctly handles infrastructure POIs (trails, bike paths) vs. venue POIs; check TripAdvisor 500 errors logged during Q2
2. **Seed NYC LLM-synthetic ratings cache** — expand `cache/ratings/llm_synthetic_new_york_ny.json` from 6 to ~50 entries covering the POIs the agent typically surfaces: Central Park, Brooklyn Bridge, AMNH, Prospect Park, Hudson River Park, Staten Island Greenbelt, Coney Island, Inwood Hill Park
3. **Run `--limit 15` smoke test** — validates full happy-path block (SF Q1–8 + NYC Q9–15) before the 150-call full run

### Full eval run

Run `python3 eval/run_week4_eval.py` (150 calls, ~5–8 hours). Fill the results table in Section 6 with the complete 30-query comparison.

### Recommended production configuration

Based on the 3-case sanity run: **OSM + LLM-Synthetic (Run 1)** as the baseline (3/3 pass, 100% recall, fastest at 44.6s). Upgrade to **Tavily + TripAdvisor (Run 5)** when both API keys are available — Run 5 provides real ratings and photos despite the current biking recall gap, which is expected to close after the classifier fix.

### Top remaining failure mode

The OSM classifier misses POIs without explicit activity tags. A "nature reserve" known locally for kayaking has no `water_sports` OSM tag — it falls into the scenic fill track even when kayaking is requested. The Run 2 vs Run 1 recall delta in `results_week4.md` will quantify how much the Tavily classifier improves this once the biking fix is in.

### Monitoring signals in production

- Alert: `routing_pass < 1.0` for any run with non-empty activities (should never happen after the iter=0 fix)
- Alert: `activity_recall < 0.5` averaged over 50 runs (signals OSM tag coverage degradation or prompt regression)
- Alert: `pct_rated < 0.5` on TripAdvisor runs (signals API quota issues or POI name-matching failures)
- Dashboard: `actual_first_poi_tool` distribution — any drift from 100% correct split is a regression signal
