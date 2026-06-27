# Data Flows — Activity-Based Day Trip Planning

Three flows, each anchored to a real user query. Read these to understand what data moves
where, what gets cached, and what API calls actually happen.

---

## Flow 1 — No activities requested (existing behavior, unchanged)

**User query:** "Plan a day in San Francisco"

```
User
  │
  │  "Plan a day in San Francisco"
  ▼
[Query Parser]
  │  city = "San Francisco, CA"
  │  activities = []              ← empty, no activities mentioned
  │  categories = ["park", "landmark", "museum", ...]
  ▼
[Knowledge Graph]
  │  KG.get_pois_for_city("San Francisco, CA")
  │  → 40–60 POIs (already indexed from OSM at startup)
  │  ← no network call, in-memory
  ▼
[ActivityClassifier]
  │  SKIPPED — activities=[], classifier is not called
  │  zero API calls
  ▼
[POI Selector — scenic-only]
  │  all slots = scenic fills ranked by composite scenic_score
  │  top 5 by score → [Baker Beach, Lands End, Golden Gate Park,
  │                     Alcatraz, Fisherman's Wharf]
  ▼
[Rating Provider]
  │  RatingProvider.enrich_batch("San Francisco", [5 selected POIs])
  │  → checks 21-day local cache first
  │  → if cache miss: 1 API call to TripAdvisor / Foursquare
  │  → adds rating, review_snippet, photos to each stop
  ▼
[Narrate Node]
  │  prompt: 5 stops, scenic quality descriptions only
  │  → LLM generates narrative, no activity claims
  ▼
Day trip: 5 scenic stops, no activity badges
```

**API calls this run:** 0 (KG in-memory) + 0 (classifier skipped) + 0–1 (rating cache)
**What the user sees:** same experience as before Week 4, no change

---

## Flow 2 — Activities requested, OSM classifier (free baseline)

**User query:** "Plan a day in San Francisco with hiking and kids activities"

```
User
  │
  │  "Plan a day in San Francisco with hiking and kids activities"
  ▼
[Query Parser]
  │  city       = "San Francisco, CA"
  │  activities = ["hiking", "kids"]
  │  categories = ["park", "nature", "family"]
  ▼
[Knowledge Graph]
  │  KG.get_pois_for_city("San Francisco, CA")
  │  → 40–60 candidate POIs  (in-memory, no network call)
  ▼
[OSMActivityClassifier]
  │
  │  For each POI, checks OSM tags already present on the POI object:
  │
  │  Lands End          leisure=nature_reserve  → matched: ["hiking"]
  │  Crissy Field       leisure=park            → matched: []
  │  Baker Beach        natural=beach           → matched: []
  │  Academy of Sciences tourism=museum         → matched: []  ← miss (OSM has no kids tag)
  │  Golden Gate Park   leisure=park            → matched: []
  │  Children's Playground amenity=playground   → matched: ["kids"]
  │
  │  No API calls. Pure in-memory tag lookup.
  │  Limitation: OSM tags are sparse — many valid hiking/kids POIs
  │  won't have the right tag → false negatives expected.
  │  This is the baseline — Tavily/Perplexity improve on this.
  ▼
[POI Selector — two-track]
  │
  │  Track 1 (activity slots, 2 requested = 2 slots):
  │    slot 1 [hiking]: Lands End
  │    slot 2 [kids]:   Children's Playground
  │
  │  Track 2 (scenic fills, 5 - 2 = 3 slots):
  │    slot 3: Baker Beach          scenic_score 0.87
  │    slot 4: Golden Gate Park     scenic_score 0.82
  │    slot 5: Fisherman's Wharf    scenic_score 0.74
  │
  │  Ordered by geography for logical day flow.
  ▼
[Rating Provider]
  │  enrich_batch on all 5 selected POIs
  │  → cache check → API call if miss → ratings, photos, snippets
  ▼
[query_poi_context]
  │  preferences = ["hiking", "kids"]
  │  Indexes Wikipedia descriptions → ChromaDB (local, no network)
  │  Retrieves per POI: semantic match score, Wikipedia evidence,
  │                     city/region (KG LOCATED_IN), nearby POIs (NEAR_POI)
  ▼
[Narrate Node]
  │  Lands End:             "We picked this for your hiking — [rating 4.7]"
  │  Children's Playground: "Perfect for kids — [rating 4.3]"
  │  Baker Beach:           scenic description
  │  Golden Gate Park:      scenic description
  │  Fisherman's Wharf:     scenic description
  ▼
Day trip: 2 activity-badged stops + 3 scenic fills

Evaluation result:
  Activity Match Recall = 2/2 = 100% (both selected stops verified by OSM tags)
  Activity Coverage     = 2/2 = 100% (hiking covered, kids covered)
  Limitation noted: Academy of Sciences missed (no OSM kids tag) — Tavily fixes this
```

**API calls this run:** 0 (classifier) + 0–1 (rating cache)

---

## Flow 3 — Activities + Tavily classify + Tavily enrich + ranking

**User query:** "Plan a day in San Francisco — scenic coastal hiking and something for kids"

Note: the user said **"scenic coastal hiking"** — that adjective phrase drives the ranker.

```
User
  │  "Plan a day in San Francisco — scenic coastal hiking and something for kids"
  ▼
[Query Parser]
  │  city         = "San Francisco, CA"
  │  activities   = ["hiking", "kids"]
  │  user_context = "scenic coastal hiking"    ← extracted adjective phrase
  ▼
[Knowledge Graph]
  │  → 40–60 candidate POIs  (in-memory, no network call)
  ▼
[TavilyActivityClassifier]
  │
  │  Search 1: "hiking in San Francisco places"
  │    → CACHE MISS: 1 Tavily call → cache written (21-day TTL)
  │    → tagged: Lands End ✓, Crissy Field ✓, Tennessee Valley ✓,
  │              Golden Gate Park ✓, Corona Heights ✓, Glen Canyon ✓
  │
  │  Search 2: "kids activities in San Francisco places"
  │    → CACHE MISS: 1 Tavily call → cache written
  │    → tagged: Academy of Sciences ✓, Golden Gate Park ✓,
  │              Children's Playground ✓, Exploratorium ✓
  ▼
[ActivityRanker — SemanticRanker]
  │  user_context = "scenic coastal hiking" → adjectives detected → SemanticRanker
  │
  │  Hiking candidates (6 POIs), ranked by similarity to "scenic coastal hiking":
  │    1. Lands End         evidence: "rugged coastal trail, ocean views"    sim: 0.91
  │    2. Tennessee Valley  evidence: "trail through valley to the beach"    sim: 0.74
  │    3. Crissy Field      evidence: "flat paved path along the bay"        sim: 0.61
  │    4. Corona Heights    evidence: "rocky scramble, city views"           sim: 0.42
  │    5. Golden Gate Park  evidence: "flat trails, mostly park paths"       sim: 0.38
  │    6. Glen Canyon       evidence: "quiet wooded trail, inland"           sim: 0.21
  │
  │  → Lands End wins hiking slot  (coastal + scenic match is strongest)
  │
  │  Kids candidates (4 POIs), ranked by rating (no adjectives for kids):
  │    1. Academy of Sciences   rating: 4.8
  │    2. Exploratorium         rating: 4.6
  │    3. Golden Gate Park      rating: 4.4
  │    4. Children's Playground rating: 4.1
  │
  │  → Academy of Sciences wins kids slot
  ▼
[POI Selector — two-track]
  │
  │  Track 1 (2 activity slots, top-ranked per activity):
  │    slot 1 [hiking]: Lands End           (rank 1 for "scenic coastal hiking")
  │    slot 2 [kids]:   Academy of Sciences  (rank 1 by rating)
  │
  │  Track 2 (3 scenic fills, from remaining POIs by scenic_score):
  │    slot 3: Baker Beach         scenic_score 0.87  (Lands End neighbors excluded)
  │    slot 4: Crissy Field        scenic_score 0.85  (hiking rank 3, good scenic fill)
  │    slot 5: Golden Gate Park    scenic_score 0.82
  ▼
[TavilyEnrichmentProvider]  ← Tavily as rating/enrichment provider
  │
  │  Bulk search: "visitor highlights reviews San Francisco attractions"
  │    → CACHE MISS: 1 Tavily call → cache written
  │
  │  LLM extraction per selected POI (~150 tokens each):
  │
  │    Lands End:
  │      rating_hint  : "consistently 4.5–4.8 stars across review sites"
  │      highlights   : ["dramatic bluff trail", "WWII ruins", "best at golden hour"]
  │      visitor_quote: "one of the most underrated hikes in all of California"
  │      photo_url    : "https://..."
  │
  │    Academy of Sciences:
  │      rating_hint  : "top-rated family attraction in SF"
  │      highlights   : ["planetarium shows", "living roof", "albino alligator"]
  │      visitor_quote: "my kids didn't want to leave"
  │      photo_url    : "https://..."
  │
  │  LLMSyntheticRatingProvider runs as fallback for any POI Tavily didn't cover
  │  (Baker Beach, Crissy Field, Golden Gate Park — rare, Tavily usually covers all)
  ▼
[query_poi_context]
  │  preferences = ["hiking", "kids"]
  │  Indexes Wikipedia descriptions for all 5 POIs → ChromaDB (local, no API call)
  │  Retrieves per POI: semantic match score, Wikipedia evidence,
  │                     city/region (KG LOCATED_IN), nearby POIs (KG NEAR_POI)
  │
  │  Lands End:
  │    match_score     : 0.91  (strong match to "hiking")
  │    wikipedia_chunk : "rugged 3.5-mile coastal trail with views of the Golden Gate"
  │    region          : "Marin Headlands area"
  │    nearby          : ["Baker Beach (0.8 mi)", "Lincoln Park (0.4 mi)"]
  │
  │  Academy of Sciences:
  │    match_score     : 0.84  (strong match to "kids")
  │    wikipedia_chunk : "natural history museum with a planetarium, aquarium, and living roof"
  │    region          : "Golden Gate Park"
  │    nearby          : ["de Young Museum (0.1 mi)", "Japanese Tea Garden (0.2 mi)"]
  ▼
[Narrate Node]
  │
  │  Lands End (Track 1, hiking — grounded in classifier + Tavily enrichment):
  │    "We chose Lands End for your scenic coastal hiking. The bluff trail
  │     offers dramatic ocean views — best at golden hour. Visitors call it
  │     'one of the most underrated hikes in California.' Rated 4.7."
  │
  │  Academy of Sciences (Track 1, kids — grounded in both):
  │    "For the kids: the Academy of Sciences is SF's top family stop — 
  │     planetarium, living roof, albino alligator. 'My kids didn't want to leave.'
  │     Rated 4.8."
  │
  │  Track 2 stops use Tavily highlights + scenic quality:
  │    Baker Beach:   "Golden Gate views from the sand. One of SF's best beach walks."
  │    Crissy Field:  "Flat waterfront path with bay views — easy after the Lands End hike."
  │    Golden Gate Park: "A great way to end the day — gardens, carousel, open space."
  ▼
Day trip — 2 activity-badged stops + 3 scenic fills

UI:
  Lands End            [Hiking]     ★ 4.7  "best at golden hour"
  Academy of Sciences  [Kids]       ★ 4.8  "kids didn't want to leave"
  Baker Beach                       ★ 4.6
  Crissy Field                      ★ 4.5
  Golden Gate Park                  ★ 4.4

Evaluation result:
  Activity Match Recall  = 2/2 = 100%
  Activity Coverage      = 2/2 = 100%  (hiking ✓  kids ✓)
  Ranking Quality        = PASS  (Lands End correctly ranked #1 for "scenic coastal hiking")
  Narrative Faithfulness = PASS  (highlights grounded in Tavily enrichment, not invented)
  vs. Flow 2 (OSM):  Academy of Sciences was missed; Lands End not ranked by description fit
```

**API calls — first run:** 2 Tavily classify + 1 Tavily enrich = 3 total
**API calls — repeat (same city + activities):** 0 (all 3 results cached 21 days)

---

## Flow 4 — Edge case: activity not available in city

**User query:** "Plan a day in Chicago with mountain biking"

```
[Query Parser]
  │  city = "Chicago, IL",  activities = ["mountain biking"]
  ▼
[TavilyActivityClassifier]
  │  Search: "mountain biking in Chicago places"
  │  → results: mostly flat bike paths, no mountain biking venues
  │  LLM extraction: 0 POIs matched to "mountain biking"
  ▼
[POI Selector]
  │  Track 1 (mountain biking): EMPTY
  │  uncovered_activities = ["mountain biking"]
  │  → fallback_note = "We couldn't find mountain biking options in Chicago
  │                     (the terrain is flat). We've filled that slot with
  │                     the best outdoor cycling alternatives instead."
  │
  │  Track 2 (scenic fills): all 5 slots from scenic score
  │    (Chicago Riverwalk, Millennium Park, Lincoln Park, Navy Pier, Maggie Daley Park)
  ▼
[Narrate Node]
  │  Opens with fallback note so user understands the plan
  │  Itinerary is all scenic — no false activity badges
  ▼
Day trip: 5 scenic stops + honest fallback explanation

Evaluation result:
  Activity Coverage     = 0/1 = 0%   ← expected for this case, not a failure
  Graceful Fallback     = PASS        ← fallback note shown, no hallucination
```

---

## Cache strategy summary

| Data | Cache location | TTL | Key |
|---|---|---|---|
| OSM POIs for city | `cache/pois_*.json.gz` | Forever (OSM is stable) | bbox coordinates |
| Tavily activity results | `cache/tavily_{city}_{activity}.json` | 21 days | city + activity |
| TripAdvisor pool | `cache/ratings/tripadvisor_{city}_pool.json` | 21 days | city |
| TripAdvisor reviews | `cache/ratings/tripadvisor_review_{id}.json` | 21 days | location_id |
| LLM synthetic ratings | `cache/ratings/llm_synthetic_*.json` | Forever | poi id |

On a repeat run of the same city + same activities: **0 API calls** from classifier,
**0 API calls** from rating provider. Only the LLM narration call runs fresh.

---

## What each provider adds over the previous

```
OSM classifier alone
  → catches POIs with explicit activity tags (leisure=cycling_path, amenity=playground)
  → misses: Academy of Sciences for kids, Crissy Field for hiking (no matching OSM tag)
  → false negative rate: high for activity-tagged POIs with generic OSM categories
  → zero API cost; good as a baseline and fallback

+ Tavily
  → adds web evidence: "hiking in San Francisco" returns Crissy Field, Marin Headlands
  → catches POIs missed by OSM tags
  → bulk: 1 search per activity per city, not per POI
  → false positive risk: nearby POI names can appear in unrelated search results
  → 1000 free searches/month; 21-day cache means repeat runs cost nothing
```

For evaluation, run both classifiers independently on the same golden cases and compare
precision/recall — that tells you exactly what Tavily adds over the free OSM baseline.
