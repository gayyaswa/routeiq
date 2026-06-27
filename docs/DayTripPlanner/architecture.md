# RouteIQ Agent — Architecture & Design Decisions

Week 3 addition: a true agentic system layered on top of the Week 2 GraphRAG pipeline.
Use this document for the Week 3 submission Google Doc.

---

## Scope (Week 3)

**In scope:** Day Trip Planner agent — LangGraph graph with human-in-the-loop interrupt, TripAdvisor/Foursquare ratings + reviews + photos, Pydantic-validated structured output, dynamic KG expansion for out-of-area cities.

**Out of scope:** real-time traffic, multi-day planning, cross-provider review aggregation, user accounts, mobile. See `docs/scope-definition.md` for full rationale.

**Advanced agentic design choices (bonus patterns):**
1. **Human-in-the-loop interrupt** (`interrupt_before=["review"]`) — canonical LangGraph approval pattern. User reviews the draft; free-text feedback re-enters the plan node with full conversation history.
2. **Structured LLM output (Pydantic)** — two-phase extraction: `bind_tools()` for the ReAct loop, then `with_structured_output(DayTripItinerary)` for validated, typed final itinerary output.
3. **TripAdvisor + Foursquare as swappable single-source providers** — `POIRatingProvider` Strategy ABC with `source_name` abstract property; every stop's `review_source` badge and `visitor_quote` prefix auto-update on provider swap. Single-source traceability is deliberate.

---

## Use Case

**"Plan a scenic day in [city]"** — city-wide day trip itinerary planner.

Example input:
> "Plan a scenic day in San Francisco — I love nature and history, 8 hours starting at 9am"

Example output: a time-slotted itinerary with stop cards (name, arrive/depart, TripAdvisor rating,
visitor quote + summary from real reviews, Wikipedia factual description, activity suggestions,
up to 5 provider photos), and an LLM-generated narrative — rendered on a Folium map.

---

## Why this is genuinely agentic (not a pipeline)

| Property | Week 2 pipeline | Week 3 agent |
|---|---|---|
| Control flow | Fixed: parse → graph → rag → narrate | Dynamic: agent decides which tools to call and in what order |
| Stop selection | Deterministic spatial join + scorer | LLM reasons about time budget, preferences, travel times |
| Multi-turn | One-shot | MemorySaver: "remove museums, add beaches" refines the same session |
| Human feedback | None | Interrupt: user approves or refines draft before narrative generates |
| Replanning | No | Agent loops back if time budget doesn't fit or user requests changes |

---

## Three Data Layers — Why Each Is Needed

The final stop card blends data from three distinct sources. Each does what the others cannot:

| Layer | Source | Provides | Why not replace with the others? |
|---|---|---|---|
| Geographic | OSM (via KG) | All city POIs — exact lat/lon, categories, Wikipedia tags | TripAdvisor `nearby_search` returns ~50 "attractions" and misses parks, viewpoints, smaller historic sites. OSM gives completeness. |
| Social quality | TripAdvisor or Foursquare | Ratings, visitor reviews, photos | OSM has no quality signal — without ratings all 80–150 POIs rank equally. Wikipedia has no reviews. |
| Factual knowledge | Wikipedia | Factual description text, thumbnail image | TripAdvisor reviews are opinions. Wikipedia provides citable facts for `why_visit`. |

These layers are fetched by separate tools in sequence:

```
find_city_pois     →  OSM/KG          all city POIs
rate_pois          →  TripAdvisor     ratings + reviews + photos (on OSM POIs)
                      or Foursquare   ratings + tips + hours (on OSM POIs)
enrich_poi_details →  Wikipedia       factual description + thumbnail (top 8 only)
estimate_visit
get_travel_time    →  internal        time schedule
```

---

## Architecture

```
User query
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  LangGraph Graph  (MemorySaver checkpointer — thread-safe)  │
│                                                             │
│  ┌──────────┐    tools fire    ┌──────────┐                 │
│  │  plan    │◄────────────────►│  tools   │  (ReAct loop)   │
│  │  (LLM +  │                  │ executor │                 │
│  │  tools)  │                  └──────────┘                 │
│  │          │   ┌─────────────────────────────────────────┐ │
│  │          │   │ with_structured_output(DayTripItinerary)│ │
│  └────┬─────┘   └─────────────────────────────────────────┘ │
│       │ validated Pydantic itinerary                        │
│       ▼                                                     │
│  ┌──────────┐   interrupt()                                 │
│  │  review  │──────────────────► USER sees draft stop cards  │
│  └────┬─────┘   resume(approved=True / feedback)            │
│       │                                                     │
│  ┌────▼─────┐                                               │
│  │ narrate  │  → LLM narrative + Folium map                 │
│  └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
```

### Nodes

| Node | Role | LangGraph type |
|---|---|---|
| `plan` | ReAct tool loop (`bind_tools`), then structured extraction (`with_structured_output`) | Custom (manual while-loop + Pydantic) |
| `review` | Calls `interrupt(draft)` — graph pauses; returns `Command(goto=...)` | Custom (interrupt node) |
| `narrate` | Calls LLM with conversation history → 3–4 sentence narrative | Custom |

### Edges

```
START → plan → review
review → narrate  (Command(goto="narrate") on approved)
review → plan     (Command(goto="plan") on refine — appends feedback HumanMessage)
narrate → END
```

---

## The 7 Agent Tools

| Tool | What it does | Data source |
|---|---|---|
| `find_city_pois(city, categories)` | KG city lookup → returns ALL OSM POIs (instant, no network) | OSM via `RouteKnowledgeGraph` |
| `select_pois_for_day(city, activities, ...)` | Two-track merge: activity-matched slots + scenic fills | `ActivityClassifier` + KG |
| `rate_pois(city, poi_list_json)` | Enriches OSM POIs with ratings + reviews + photos; composite score | TripAdvisor / LLM-synthetic (via `RatingsFactory`) |
| `query_poi_context(preferences, rated_pois_json)` | Indexes Wikipedia descriptions → ChromaDB; retrieves KG-enriched context per POI | ChromaDB (local) + KG |
| `enrich_poi_details(poi_name, city)` | Wikipedia factual description + thumbnail image for a named POI | Wikipedia |
| `estimate_visit_duration(category, subtype)` | Heuristic minutes per stop type | Built-in lookup table |
| `search_poi_by_name(name, city)` | Nominatim geocoding — resolves user-named landmarks during refinement | OpenStreetMap Nominatim |

### find_city_pois — KG-first, geographic completeness

Queries `RouteKnowledgeGraph.get_pois_for_city()` (in-memory, instant) — returns ALL
OSM-verified POIs, not just those similar to the query. A great museum is never missed
because the query was "parks."

For cities outside the Bay Area, `app.py` runs a pre-flight before the agent starts:

```
1. Check kg.known_cities() — is city already indexed?
2. If not → st.spinner("Fetching POIs for {city}...")
3. POIFinder.find_pois_in_bbox() → Overpass fetch (one-time, cached to disk)
4. kg.add_city_pois(city, lat, lon, pois) → adds City node to in-memory KG
5. Agent starts → find_city_pois always hits KG (no network inside the agent)
```

### rate_pois — social quality layer

Takes the full OSM POI list and enriches it with provider data:

```
OSM POIs (80–150)
    │
    ▼  RatingsFactory.create()  (RATING_PROVIDER env var)
    │
    ├── TripAdvisor (primary):
    │     1 nearby_search → pool of ~50 attractions (cached 21 days per city)
    │     Per matched POI:
    │       /reviews?sort=HELPFUL → top 3 reviews ≥80 chars (cached per location_id)
    │       /photos → up to 5 photos, large→medium fallback (cached per location_id)
    │     Rating: 1–5 (no normalization needed)
    │
    └── Foursquare (secondary, RATING_PROVIDER=foursquare):
          3 category calls: sights/arts/historic (cached 21 days per city)
          Per matched POI: tips[0] as snippet, hours
          Rating: 0–10 → ÷2 → 0–5.0 normalized
    │
    ▼  ChromaDB ephemeral merge (name similarity + 100m proximity fallback)
    │
    ▼
RatedPOI: OSM data +
  rating (0–5), review_count,
  all_snippets (up to 3 reviews, ≥80 chars),
  review_source ("TripAdvisor" | "Foursquare"),
  photo_urls (up to 5)
```

**Why `POIRatingProvider` not `POIEnrichmentProvider`?** Ratings are the primary *filtering* signal —
the class name reflects the ranking use case. Reviews and photos are additional signals the provider
returns and are passed through to the stop card.

### Why ChromaDB for the OSM↔Provider name merge

| OSM name | Provider name |
|---|---|
| Alcatraz Island | Alcatraz |
| de Young Museum | de Young Fine Arts Museums of San Francisco |
| Angel Island State Park | Angel Island |

Character-level fuzzy matching fails — strings are too different. ChromaDB embedding similarity
handles name variants, abbreviations, partial matches. Reuses existing project dependency.

Fallback: haversine proximity ≤ 100 m for cases where embedding similarity fails
(e.g., a POI known by completely different names in OSM vs. the provider).

### API call budget

| Scenario | TripAdvisor calls | Foursquare calls |
|---|---|---|
| First query for a new city | 1 pool + N×2 per matched POI | 3 (one per bucket) |
| Any repeat query (cache hit) | 0 | 0 |
| Full demo (5 Bay Area cities, pre-seeded) | 0 live calls | 0 live calls |
| Cache TTL | 21 days | 21 days |

### Composite ranking score (same formula for both providers)

```
score = 0.4 × (rating / 5.0)
      + 0.3 × log(1 + review_count) / log(1 + 10000)
      + 0.3 × (0.1 if wikipedia_tag else 0.0)
```

POIs with `rating < 3.8` AND `review_count < 20` are dropped before scoring.

---

## Memory & Multi-turn Refinement

`MemorySaver` checkpoints the full `DayTripState` (messages + draft + approval status) after
every node. When the user types "remove museums, add more nature":

1. Streamlit sends `Command(resume={"approved": False, "feedback": "remove museums..."})` 
2. `review` node appends feedback as a HumanMessage to state
3. `Command(goto="plan")` re-enters plan — LLM sees full prior tool call history and re-plans
4. New draft surfaces at interrupt; user approves or refines again

---

## Human-in-the-Loop Pattern

```python
def _review(state: DayTripState) -> Command:
    decision = interrupt(state["draft_itinerary"])   # graph pauses; UI shows draft cards
    if decision.get("approved"):
        return Command(goto="narrate", update={"approved": True})
    feedback = decision.get("feedback", "Please refine.")
    return Command(
        goto="plan",
        update={"messages": [HumanMessage(content=f"Refine: {feedback}")]},
    )
```

In Streamlit:
- Background thread runs `graph.stream(initial_state, config)` → thread finishes at interrupt
- `graph.get_state(config).next` contains `"review"` → render draft stop cards
- User clicks **Approve** → `graph.invoke(Command(resume={"approved": True}), config)`
- User types feedback → `graph.stream(Command(resume={"approved": False, "feedback": text}), config)`

---

## Reuse from Week 2

| Week 2 component | How reused in Week 3 |
|---|---|
| `POIFinder` | Pre-flight `find_pois_in_bbox()` for out-of-area cities |
| `WikipediaFetcher` | `enrich_poi_details` tool wraps `.enrich()` |
| `RouteKnowledgeGraph` | `find_city_pois` tool + `add_city_pois()` for dynamic KG expansion |
| `MapBuilder` | Renders final itinerary Folium map |
| `LLMFactory` | LLM instance created in `_make_llm()` — swappable via `LLM_PROVIDER` env var |
| ChromaDB | Reused ephemerally for provider name merge |
| `cache/pois/bay_area_all.json.gz` | Master cache hit in `find_pois_in_bbox` for Bay Area |

---

## Week 4 — Activity-Based Planning Layer

### What changed

Week 4 adds an **activity selection layer** that intercepts POI discovery before enrichment. When
the user requests activities (hiking, biking, swimming, kayaking, kids, picnic), the agent calls
`select_pois_for_day` instead of `find_city_pois`. The two-track merge ensures activity-matched
stops never crowd out scenic variety.

![Activity pipeline data flow and bug locations fixed in Week 4](./images/eval_activity_pipeline.png)

### The 6th tool — select_pois_for_day

```
User sets activities=["hiking", "swimming"]
    │
    ▼
select_pois_for_day(city, requested_activities, user_context, total_stops)
    │
    ├── ActivityClassifier.classify_batch(city, all_pois, activities)
    │       OSMActivityClassifier:  tag lookup → peak→hiking, beach→swimming (instant, 0ms)
    │       TavilyActivityClassifier: web search per POI name → LLM extracts activity signal
    │
    ├── ActivityRanker.rank(classified_pois, user_context)
    │       SemanticRanker:  cosine sim between user_context and poi description
    │       ScoredRanker:    rating × recency weight (when ratings already available)
    │
    └── ActivityPOISelector.select(classified, activities, total_stops)
            Track 1 (activity slots):  proportional budget — 1 slot for 1-4 matches,
                                        2 slots for 5-10 matches, 3+ for larger pools
            Track 2 (scenic fills):    top unmatched POIs by scenic score fill remaining slots
            Output field per stop:
              track              = "activity" | "scenic"
              matched_activities = ["hiking"] or []
              activity_evidence  = "OSM tag: peak" or "Tavily: known for coastal hikes"
```

### Tool routing — the key behavioral signal

```
activities non-empty  →  select_pois_for_day   (classifier runs, activity-aware two-track merge)
activities empty      →  find_city_pois         (scenic-only path, same as Week 3)
```

The `_plan` node's iter=0 nudge is activity-aware: if activities are set and the LLM hesitates
on the first iteration, it is explicitly nudged to call `select_pois_for_day` — never
`find_city_pois`.

### Updated ReAct loop — Improvement 9

![ReAct loop before vs after Improvement 9 — 12 iterations → 2-3](./images/eval_react_loop_fix.png)

`rate_pois` now pre-populates `visit_duration_min` from the same lookup table as
`estimate_visit_duration`. The V2 prompt explicitly tells the LLM: *"Do NOT call
enrich_poi_details or estimate_visit_duration — data is already present."*

Result: 12 iterations (hit cap, never stopped naturally) → 2–3 iterations (stops after `rate_pois`).
Plan time: ~56s → ~36s total react time for SF swimming.

### Expanded rating providers

`routeiq/ratings/` now has 5 providers, all behind `RatingsFactory.create(RATING_PROVIDER)`:

| Provider | `RATING_PROVIDER` | What it returns |
|---|---|---|
| `LLMSyntheticRatingProvider` | `llm_synthetic` | Synthetic ratings from Wikipedia description — default, no key needed |
| `TripAdvisorRatingProvider` | `tripadvisor` | Real ratings, up to 5 photos, 3 review snippets |
| `TavilyEnrichmentProvider` | `tavily_enrichment` | Web-searched ratings + snippets (no TA key required) |
| `NullRatingProvider` | (fallback) | Empty enrichment — agent works with no keys |

### New package — routeiq/activities/

```
routeiq/activities/
  base.py              ActivityClassifier ABC — classify_batch(city, pois, activities) → list[ClassifiedPOI]
  osm_classifier.py    OSMActivityClassifier — tag lookup, zero latency, zero API calls
  tavily_classifier.py TavilyActivityClassifier — web search + LLM extraction
  ranker.py            ActivityRanker — semantic + scored ranking strategies
  factory.py           create_activity_classifier(ACTIVITY_PROVIDER), create_ranker()
```

### Timing instrumentation — routeiq/timing.py

`timing.log(msg)` appends timestamped lines to `logs/timing.log`; `timing.clear()` resets at
each planning run. Lines go to file only (never stdout), so the UI is unaffected.
Used to diagnose the 12-iteration problem and verify the fix.

### Eval framework — eval/

```
eval/
  langsmith_dataset.py      30 golden queries: WEEK4_EVAL_QUERIES, ACTIVITY_KEYWORDS
  tool_routing_queries.py   8 tool routing golden cases (4 with activities, 4 without)
  evaluators.py             score_tool_routing(), score_activity_recall(),
                            score_enrichment_quality(), score_activity_match_quality(),
                            ActivityEvaluator class
  run_week4_eval.py         5-config sweep (150 calls) → eval/results_week4.md
  run_tool_routing_eval.py  Fast routing check (8 calls) → eval/results_tool_routing.md
```

Judge methods: code-based (routing, recall, enrichment) + LLM-as-judge (match quality 1–5).

---

## Design Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Custom graph (not `create_react_agent` prebuilt) | Need clean interrupt point mid-graph; prebuilt runs to completion |
| 2 | `MemorySaver` checkpointer | Zero infrastructure; multi-turn refinement with full history |
| 3 | `interrupt_before=["review"]` | User corrects draft before expensive LLM narrative generation |
| 4 | OSM → provider → Wikipedia in separate tools | Three data sources serve different trust levels in the prompt (geographic, social, factual) |
| 5 | TripAdvisor as primary provider | Higher quality reviews + up to 5 photos; user has API key |
| 6 | Foursquare as swappable secondary | Strategy pattern — one env var swap; no code changes required |
| 7 | `source_name` on `POIRatingProvider` ABC | Every stop's `review_source` badge and `visitor_quote` prefix auto-update on swap |
| 8 | Reviews: `sort=HELPFUL` + min 80 chars | Top-upvoted reviews are most substantive; filters one-liners before LLM context |
| 9 | Two-phase plan node (`bind_tools` → `with_structured_output`) | ReAct needs free-form tool calling; final extraction needs Pydantic validation — can't combine in one LLM call |
| 10 | 21-day cache TTL | Ensures cache outlives any evaluation/demo window |
| 11 | `NullRatingProvider` fallback | Agent works without any API key; graceful degradation |
