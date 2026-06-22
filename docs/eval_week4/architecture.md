# Architecture — Activity-Based Day Trip Planning

The best way to understand this architecture is to follow a real user request through it.
Every design decision below is explained by what it enables for the user.

---

## The request we'll follow

> "Plan a day in San Francisco — I want to do some hiking and bring my kids"

---

## Step 1 — Parse: what does the user actually want?

The query parser extracts two kinds of intent from this sentence:

```
city        = "San Francisco, CA"
activities  = ["hiking", "kids"]       ← things to DO
categories  = ["park", "nature"]       ← inferred place types
n_stops     = 5                        ← default
```

**Why two fields?** "Hiking" is an activity — it says what the user wants to do. "Park" is a
category — it describes a type of place. A park can exist without hiking trails. The agent
needs to know both to serve the user correctly.

The parser is the only place in the pipeline that reads the raw user text.
Everything downstream works from structured fields.

---

## Step 2 — Graph: get candidate POIs from the city

The existing Knowledge Graph (KG) returns all indexed POIs for San Francisco — around 40–60
candidates across beaches, parks, landmarks, museums, and more.

```
KG.get_pois_for_city("San Francisco, CA")
→ [Lands End, Crissy Field, Baker Beach, Academy of Sciences,
   Golden Gate Park, Alcatraz, Fisherman's Wharf, ...]
```

At this point every POI is just a dot on a map — coordinates, a name, and an OSM category.
No quality signal yet. No activity tags yet.

---

## Step 3 — Classify: which POIs actually support the requested activities?

This is the new step added in Week 4.

The `ActivityClassifier` looks at the full candidate list and answers one question per POI
per activity: **does evidence exist that people do this activity here?**

```
ActivityClassifier.classify_batch(
    city     = "San Francisco, CA",
    pois     = [Lands End, Crissy Field, Baker Beach, ...],
    activities = ["hiking", "kids"]
)
```

Result — each POI gets a `matched_activities` tag:

```
Lands End           → matched_activities: ["hiking"]
Crissy Field        → matched_activities: ["hiking", "kids"]
Baker Beach         → matched_activities: []
Academy of Sciences → matched_activities: ["kids"]
Golden Gate Park    → matched_activities: ["hiking", "kids"]
Alcatraz            → matched_activities: []
Fisherman's Wharf   → matched_activities: []
```

**This is a classification problem, not a rating problem.** The answer is binary:
evidence exists or it doesn't. The classifier does not score how good Lands End is for
hiking — it only determines whether hiking evidence exists.

Three classifiers are available, each using a different evidence source:

| Classifier | Evidence source | API calls |
|---|---|---|
| `OSMActivityClassifier` | OSM tags already on the POI (free) | 0 |
| `TavilyActivityClassifier` | Web search: "hiking in San Francisco" | 1 per activity per city, cached 21 days |
| `PerplexityActivityClassifier` | AI synthesis: one query covers all activities | 1 per city, cached 21 days |

All three implement the same `ActivityClassifier` interface. The rest of the pipeline
doesn't know or care which one is running — swapped via `ACTIVITY_PROVIDER` env var.

---

## Step 3b — Rank: pick the best POI per activity

Classification answers "does hiking exist here?" — a binary yes/no.
It does not answer "which of the 6 hiking POIs is the best fit for *this* user?"

That is the ranking step. After classification gives us candidates per activity, we rank
them before handing them to the selector.

**Example:** User says "scenic coastal hiking" — 6 SF POIs are tagged `[hiking]`:

```
Candidates for hiking slot:
  Lands End           evidence: "rugged coastal trail with ocean views"
  Crissy Field        evidence: "flat paved path along the bay"
  Tennessee Valley    evidence: "moderate trail through valley to the beach"
  Golden Gate Park    evidence: "multiple trails, mostly flat"
  Corona Heights      evidence: "short rocky scramble, city views"
  Glen Canyon Park    evidence: "quiet wooded trail, off the beaten path"
```

The ranker scores each candidate against two signals:

**Signal 1 — User description alignment:**
The user said "scenic coastal hiking". Semantic similarity between that phrase and the
activity evidence text scores Lands End and Tennessee Valley highest. Glen Canyon Park
(wooded, inland) scores lowest even though it has a valid hiking tag.

**Signal 2 — Rating:**
If a rating is available (from TripAdvisor, Foursquare, or Tavily enrichment), it
contributes to the final score:

```
activity_rank_score = 0.6 × description_similarity + 0.4 × normalized_rating
```

If no rating is available yet, similarity score alone decides.

**Result:** Lands End selected for the hiking slot — best match to "scenic coastal".
The other 5 hiking POIs are not wasted: they remain eligible as scenic fills if their
scenic_score is high enough.

```
ActivityRanker.rank(
    candidates     = [Lands End, Crissy Field, Tennessee Valley, ...],
    activity       = "hiking",
    user_context   = "scenic coastal hiking",   ← extracted from original query
    ratings        = {poi_id: 4.7, ...}          ← from enrichment if already run
) → ranked list, best first
```

Three ranker strategies, swapped via `ACTIVITY_RANKER` env var:

| Ranker | How it ranks | Best when |
|---|---|---|
| `RatingRanker` | Sort by rating descending | Ratings available, user gave no specific adjectives |
| `SemanticRanker` | Embedding similarity: user description ↔ activity evidence | User gave adjectives ("scenic", "challenging", "family-friendly") |
| `LLMRanker` | LLM picks best given full user context | Complex preferences, multiple conflicting signals |

Default: `SemanticRanker` when user context has adjectives; `RatingRanker` otherwise.

---

## Step 4 — Select: build the itinerary in two tracks

Now the selector decides which POIs make it into the day trip.
Each activity slot takes the **top-ranked** candidate from Step 3b.

```
POISelector.select(
    classified_pois    = [...all 40–60 POIs with tags...],
    requested_activities = ["hiking", "kids"],
    total_stops        = 5
)
```

**Track 1 — Activity slots** (guaranteed, 1 per requested activity, max 3):
```
requested = ["hiking", "kids"]  →  2 activity slots

slot 1 (hiking): Lands End           matched_activities: ["hiking"]
slot 2 (kids):   Academy of Sciences  matched_activities: ["kids"]
```

**Track 2 — Scenic fill** (remaining slots by composite scenic score):
```
total_stops=5, activity_slots=2  →  3 scenic fill slots

slot 3: Baker Beach         scenic_score: 0.87
slot 4: Golden Gate Park    scenic_score: 0.82
slot 5: Fisherman's Wharf   scenic_score: 0.74
```

The user always gets their requested activities honored. The scenic fills round out the day
with high-quality stops that don't need to match any activity.

**Default slot logic:**
- Activities requested → `min(len(activities), 3)` guaranteed activity slots
- No activities → 0 activity slots, all scenic (existing behavior, unchanged)
- User specifies a count ("3 stops for hiking") → use that count

---

## Step 5 — Enrich: add quality signals to every selected stop

The rating provider runs on all 5 selected POIs — Track 1 and Track 2 alike.

```
RatingProvider.enrich_batch(city="San Francisco, CA", pois=[5 selected])
→ each POI gains: rating, review_snippets, photos, visitor highlights
```

**Tavily is now also a rating/enrichment provider**, not just a classifier.
It fetches real web content about each POI and extracts quality signals from it —
without needing a TripAdvisor or Foursquare API key.

All enrichment providers implement the same `POIRatingProvider` ABC,
swapped via `RATING_PROVIDER` env var:

| Provider | What it fetches | Best for |
|---|---|---|
| `TripAdvisorRatingProvider` | Rating, 3 reviews, 5 photos | Rich data when key is available |
| `FoursquareRatingProvider` | Rating, tips, category | Fallback when TripAdvisor unavailable |
| `TavilyEnrichmentProvider` | Web-sourced description, highlights, quality signals | No third-party key needed; works for any POI worldwide |
| `LLMSyntheticRatingProvider` | LLM-generated descriptions | Offline / no API access; used as eval baseline |
| `NullRatingProvider` | Nothing — POI shown with name + location only | Graceful degradation |

**How `TavilyEnrichmentProvider` works (bulk, not per-POI):**

```
enrich_batch(city, pois):
  # One search covers multiple POIs — bulk pattern, same as TripAdvisor nearby_search
  search = tavily.search(f"visitor reviews highlights {city} attractions")
  
  # Second search per POI only if first search didn't return enough for that POI
  # (≤2 cache misses per city per session in practice)

  For each POI, LLM extracts from matching results:
    → rating_hint  : "highly rated", "4+ stars across sources", "mixed reviews"
    → highlights   : ["best at sunset", "free entry", "arrive early — gets crowded"]
    → visitor_quote: "one of the best coastal walks I've ever done"
    → photo_url    : first image URL from Tavily result (if present)
  
  cache: per-POI result, 21-day TTL
```

Tavily enrichment gives **grounded descriptions** from real web sources — not invented
by the LLM. This directly improves narrative faithfulness, a key eval metric.

**After enrichment, each stop carries both classification and quality signals:**

```
Lands End
  matched_activities : ["hiking"]                  ← from ActivityClassifier (Step 3)
  activity_evidence  : "coastal hiking trail"       ← from ActivityClassifier
  rating_hint        : "consistently 4.5+ stars"   ← from TavilyEnrichmentProvider (NEW)
  highlights         : ["dramatic ocean views",     ← from TavilyEnrichmentProvider (NEW)
                        "best at golden hour",
                        "5-mile loop or short out-and-back"]
  visitor_quote      : "one of SF's hidden gems"   ← from TavilyEnrichmentProvider (NEW)
  photo_url          : "https://..."               ← from TavilyEnrichmentProvider (NEW)

Academy of Sciences
  matched_activities : ["kids"]
  rating_hint        : "top-rated family attraction"
  highlights         : ["planetarium", "living roof", "aquarium"]
  visitor_quote      : "kids were mesmerized for hours"
  photo_url          : "https://..."
```

---

## Step 6 — Narrate: different voice for each track

The narrate node knows which track each stop came from.

**Track 1 stops — lead with the activity:**
> "We picked Lands End for your hiking. The coastal trail is one of the most-praised in
> the city — reviewers specifically mention it's manageable for kids too. Rated 4.7."

**Track 2 stops — lead with scenic quality:**
> "Baker Beach rounds out your afternoon with some of the best Golden Gate Bridge views
> in the city. Rated 4.6 — consistently called a 'must-see' by visitors."

The narrate prompt is explicitly constrained:
- Activity claims must be backed by `activity_evidence` — never invented
- Scenic claims must be backed by `review_snippet` or rating — never invented

---

## Step 7 — Graceful fallback (when an activity isn't available)

If the user asks for "mountain biking" in Chicago (a flat city), Track 1 comes back empty
for that activity. The selector does not silently drop it.

```
uncovered_activities = {"mountain biking"}
→ fallback_note = "We couldn't find mountain biking options in Chicago.
                   We've filled that slot with the best outdoor alternatives instead."
```

The user sees the fallback note before the itinerary. They know why the plan looks the way
it does. No hallucination, no silent failure.

---

## How the pieces fit together

```
                    User query
                        │
              ┌─────────▼──────────┐
              │   Query Parser      │  city, activities, user_context, n_stops
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │  Knowledge Graph    │  40–60 candidate POIs (in-memory, no API)
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │ ActivityClassifier  │  binary tag per POI per activity
              │  OSM / Tavily /     │  "does hiking exist here? yes/no"
              │  Perplexity         │  1 search/activity/city, cached 21 days
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │  ActivityRanker     │  within each activity's candidate pool:
              │  Semantic /         │  score = description_fit + rating
              │  Rating / LLM       │  pick best match per activity slot
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │    POI Selector     │  Track 1: top-ranked activity POIs (guaranteed)
              │  two-track merge    │  Track 2: scenic fills (by composite score)
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │  Rating Provider    │  real quality signals for every selected POI
              │  TripAdvisor /      │  rating, highlights, visitor quote, photos
              │  Foursquare /       │  ← Tavily now lives here too (NEW)
              │  Tavily / LLM       │
              └─────────┬──────────┘
                        │
              ┌─────────▼──────────┐
              │   Narrate Node      │  Track 1: activity evidence + quality signals
              │                     │  Track 2: scenic quality + rating
              │                     │  all claims grounded in provider data
              └─────────┬──────────┘
                        │
                   Day trip plan
              stops + narrative + activity badges + photos
```

---

## Why ActivityClassifier and RatingProvider are separate

They answer different questions:

| | ActivityClassifier | RatingProvider |
|---|---|---|
| Question | "Can I do hiking here?" | "How good is this place?" |
| Answer | Binary — yes / no | Scalar — 4.2 stars |
| Used for | Filtering / selection | Ranking / display |
| Ground truth | Objective (evidence-based) | Subjective (opinions) |
| Evaluation | Precision / Recall | Agreement with human labels |

Mixing them would conflate filtering with ranking, making both worse.
Keeping them separate means each can be swapped, improved, or evaluated independently.

---

## Why Tavily appears in both layers

Tavily is a web search tool. It is useful at two different points in the pipeline for
different reasons — this is intentional, not duplication:

| Layer | Role | What Tavily does there |
|---|---|---|
| `ActivityClassifier` | Filtering | "hiking in SF" → finds which POIs are mentioned as hiking spots → binary tag |
| `RatingProvider` | Enrichment | "[POI name] SF visitor reviews" → extracts quality signals, highlights, quotes |

The queries are different. The outputs are different. The cache keys are different.
Using Tavily in both places costs at most 2–4 extra cached searches per city — negligible.

---

## LLM Synthetic enrichment — still in the picture

`LLMSyntheticRatingProvider` remains available alongside Tavily enrichment.
It is not replaced — it serves a specific purpose:

- **Offline / no API access** — works with zero external calls, useful for local dev and tests
- **Eval baseline** — eval run with `RATING_PROVIDER=llm_synthetic` establishes the floor
  before any real data is introduced
- **POI coverage fallback** — if Tavily returns no useful results for an obscure POI,
  LLM synthetic fills the gap rather than leaving the stop card empty

In the eval, running both providers on the same golden dataset directly measures the
quality lift Tavily enrichment provides over pure LLM synthesis.
