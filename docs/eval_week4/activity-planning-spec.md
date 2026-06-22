# Activity-Based Day Trip Planning — Feature Spec & Eval Plan

## What this feature is

Users can now specify **activities** they want to do (biking, hiking, kids activities) in
addition to or instead of place types (beaches, parks, museums). The agent selects POIs in
two tracks: activity-matched POIs first (guaranteed slots), then high-quality scenic fills
for the remaining slots.

---

## Default Slot Logic

| Situation | Activity slots | Scenic fill slots |
|---|---|---|
| User requests activities | `min(len(activities), 3)` — 1 per activity, max 3 | remaining up to total_stops (default 5–6) |
| User requests no activities | 0 | all stops by scenic/composite score |
| User requests activities + explicit count ("3 stops for hiking") | as specified | remaining |

**Example:** 5-stop day trip, user says "biking and hiking" → 2 activity slots + 3 scenic fills.

Activity slots are guaranteed — they will always appear in the itinerary if POIs exist in that
city for those activities. Scenic fills are best-effort.

---

## Use Cases

### UC-1 — Single activity, happy path
**Input:** "Plan a day in San Francisco with hiking"
**Expected:**
- ≥1 stop explicitly matched to hiking (Lands End, Marin Headlands, etc.)
- Remaining stops scenic fills (beaches, landmarks, viewpoints)
- Narrative calls out the hiking POI with activity evidence: "We picked Lands End for your hiking — reviewers consistently mention the coastal trail"
- Activity badge shown in UI: `[Hiking]`

---

### UC-2 — Multiple activities, happy path
**Input:** "Plan a day in San Francisco: biking, hiking, and something for kids"
**Expected:**
- 3 activity slots, 1 per activity (Crissy Field → biking, Lands End → hiking, Academy of Sciences → kids)
- 2–3 scenic fills
- All 3 requested activities covered (Activity Coverage = 100%)
- Each activity-matched stop has evidence badge in UI

---

### UC-3 — Activities + explicit place types
**Input:** "Plan a day in Seattle: a couple of beaches and outdoor hiking"
**Expected:**
- OSM category search returns beach POIs and park/trail POIs
- Activity classifier runs on all candidates; hiking-tagged ones get Track 1 slots
- Beach POIs without hiking tag fill remaining slots by scenic score
- No beach is labeled `[Hiking]` unless reviews actually confirm hiking there

---

### UC-4 — Activity not well-represented in city (edge case)
**Input:** "Plan a day in Chicago with mountain biking"
**Expected:**
- Classifier finds no POIs with mountain biking evidence (Chicago is flat)
- Agent does NOT hallucinate mountain biking options
- Graceful fallback: "We couldn't find mountain biking in Chicago. We've included cycling-friendly spots instead." + fills all slots with scenic/cycling-friendly POIs
- Activity Coverage metric = 0% for mountain biking (expected, not a failure)

---

### UC-5 — Activity partially available (edge case)
**Input:** "Plan a day in San Francisco: rock climbing and picnicking"
**Expected:**
- Rock climbing: 1–2 spots (Mission Cliffs indoor, Stinson Beach area)
- Picnicking: multiple matches (Dolores Park, Golden Gate Park)
- Both activities covered despite differing availability
- Narrative does not overclaim — "limited rock climbing options; we found one indoor facility"

---

### UC-6 — No activities mentioned (existing behavior, no change)
**Input:** "Plan a day in San Francisco"
**Expected:**
- 0 activity slots, all scenic fills
- Existing composite score selects POIs exactly as before
- Activity classifier is NOT called (no unnecessary API calls)
- Behavior identical to current Week 3 agent

---

### UC-7 — All activities requested but no slots specified (default logic)
**Input:** "I want to do biking, hiking, swimming, and kayaking in Seattle"
**Expected:**
- 3 activity slots (cap at 3 even though 4 activities requested)
- Top 3 activities by evidence strength get slots; 4th noted in narrative as "limited time"
- 2–3 scenic fills
- Agent explains why not all 4 were included

---

### UC-8 — Adversarial / out-of-scope (guardrail)
**Input:** "Plan a day in SF doing parkour on rooftops and urban exploration of abandoned buildings"
**Expected:**
- Agent declines the specific activities (unsafe/illegal)
- Offers alternative: "We can suggest free-running-friendly parks or urban photography spots instead"
- Does not return 0 results with no explanation

---

## How the Pipeline Handles Activities

```
[parse]     extract city, categories, activities, n_stops (default 5)
[graph]     OSM POIs for all relevant categories
[classify]  ActivityClassifier.classify_batch(city, pois, activities)
            → each POI tagged: poi.matched_activities = ["hiking"] or []
[select]    Track 1: POIs where matched_activities ∩ requested ≠ ∅  (activity slots)
            Track 2: remaining POIs by composite scenic score        (scenic fills)
            merge → ordered by geography for a logical day flow
[enrich]    RatingProvider.enrich_batch() on ALL selected POIs
            ratings, photos, review snippets for every stop
[narrate]   Track 1 stops: cite activity evidence + rating
            Track 2 stops: cite scenic quality + rating
```

---

## Activity Providers

| Provider | Mechanism | Bulk fetch strategy | Cost |
|---|---|---|---|
| `OSMActivityClassifier` | Static OSM tag → activity map | Zero API calls | Free |
| `TavilyActivityClassifier` | Web search per `(city, activity)` | 1 search/activity/city, 21-day cache | ~$0.01/city |
| `PerplexityActivityClassifier` | AI synthesis per city | 1 query/city covers all activities, 21-day cache | ~$0.01/city |

Provider is controlled by `ACTIVITY_PROVIDER` env var. Default: `osm` (free baseline).
Tavily and Perplexity layer on top for richer evidence.

---

## Evaluation Plan (Week 4)

### Eval one-liner

> I will measure activity match recall, activity coverage, narrative faithfulness, itinerary
> coherence, and p95 latency on the RouteIQ Day Trip Planner using a golden dataset of 30
> cases covering activity-based queries across SF, Seattle, NYC, and Chicago — with
> Perplexity-labeled ground truth and OSM as baseline. Pass bar: 80% activity match recall,
> 90% coverage, 85% faithfulness, p95 < 45s. Delta reported from baseline (OSM-only) to
> post-improvement (Tavily-enriched).

### Metrics

| Metric | Type | Definition | Pass bar |
|---|---|---|---|
| Activity Match Recall | Code-based | % of itinerary POIs with verified evidence for ≥1 requested activity | ≥ 80% |
| Activity Coverage | Code-based | % of requested activities served by ≥1 POI in the itinerary | ≥ 90% |
| Graceful Fallback Rate | Code-based | % of UC-4/UC-8 cases that return a fallback explanation instead of empty/wrong results | 100% |
| Narrative Faithfulness | LLM-as-judge | Narrative claims only activities present in classifier evidence | ≥ 85% |
| p95 Latency + Cost/run | LangSmith | End-to-end planning time + token spend | < 45s, < $0.10 |

### Golden Dataset — 30 cases

| Scenario type | Count | Drawn from |
|---|---|---|
| Happy path (UC-1, UC-2, UC-3) | 15 | Hand-crafted queries across SF, Seattle, NYC, Chicago |
| Edge cases (UC-4, UC-5, UC-7) | 9 | Queries where activity availability is limited or mixed |
| Known failures | 5 | Queries where current agent returns generic stops with no activity evidence |
| Adversarial (UC-8) | 1 | Unsafe/out-of-scope activity request |

**Labeling method:** For each case, query Perplexity:
> "In [city], which specific venues support [activities]? List venue names and which
> activities apply. Cite sources."

Perplexity's cited answer becomes the reference label for `ground_truth_activities` per POI.
Dataset stored in LangSmith (not CSV) under project `routeiq-week4`.

### Baseline vs. Post-improvement

| Run | Provider | What it measures |
|---|---|---|
| Baseline | `OSMActivityClassifier` | What OSM tags alone can classify (free, always available) |
| Run 2 | `TavilyActivityClassifier` | Lift from real web search evidence |
| Run 3 | `PerplexityActivityClassifier` | Lift from AI-synthesized evidence |

Compare all three on the same 30 cases. Report delta per metric per provider.
Identify which failure clusters each provider fixes and which remain.

### Failure categories to watch for

| Failure mode | Root cause | Metric it hits |
|---|---|---|
| Wrong POI tagged as activity-match | Classifier false positive (web result was about nearby place) | Precision drop |
| Valid POI missed | Classifier false negative (name mismatch, sparse web results) | Recall drop |
| Narrative overclaims activity | Narrate node not constrained to classifier evidence | Faithfulness drop |
| All slots scenic, no activity match | `filter_pois_by_activities` tool not called or misses city coverage | Coverage drop |
| Empty result on edge case city | No graceful fallback path in agent | Fallback Rate drop |
