# RouteIQ Agent — Architecture & Design Decisions

Week 3 addition: a true agentic system layered on top of the Week 2 GraphRAG pipeline.
Use this document for the Week 3 submission Google Doc.

---

## Use Case

**"Plan a scenic day in [city]"** — city-wide day trip itinerary planner.

Example input:
> "Plan a scenic day in San Francisco — I love nature and history, 8 hours starting at 9am"

Example output: a time-slotted itinerary with stop cards (name, arrive/depart, rating,
review snippet, Wikipedia description + image), a Foursquare-quality-filtered POI ranking,
and a Claude-generated narrative — all rendered on a Folium map.

---

## Why this is genuinely agentic (not a pipeline)

| Property | Week 2 pipeline | Week 3 agent |
|---|---|---|
| Control flow | Fixed: parse → graph → rag → narrate | Dynamic: agent decides which tools to call and in what order |
| Stop selection | Deterministic spatial join + scorer | Agent reasons about time budget, preferences, travel times |
| Multi-turn | One-shot | MemorySaver: "remove museums, add beaches" refines the same session |
| Human feedback | None | Interrupt: user approves or refines draft before narrative generates |
| Replanning | No | Agent loops back if time budget doesn't fit |

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
│  └────┬─────┘                                               │
│       │ draft itinerary JSON                                │
│       ▼                                                     │
│  ┌──────────┐   interrupt()                                 │
│  │  review  │──────────────────► USER sees draft            │
│  └────┬─────┘   resume(approved=True / feedback)            │
│       │                                                     │
│  ┌────▼─────┐                                               │
│  │ narrate  │  → NarrativeChain + MapBuilder                │
│  └──────────┘                                               │
└─────────────────────────────────────────────────────────────┘
```

### Nodes

| Node | Role | LangGraph type |
|---|---|---|
| `plan` | ReAct tool loop: LLM + bound tools, iterates until draft is ready | Custom (manual while-loop) |
| `review` | Calls `interrupt(draft)` — graph pauses, user sees draft itinerary | Custom (interrupt node) |
| `narrate` | Calls `NarrativeChain` on approved stops → final narrative + map | Custom |

### Edges

```
START → plan → review
review → narrate  (if approved)
review → plan     (if refine — appends user feedback to messages)
narrate → END
```

---

## The 5 Agent Tools

| Tool | What it does | Wraps |
|---|---|---|
| `find_city_pois(city, categories)` | KG city lookup → returns OSM POIs (instant, no network) | `RouteKnowledgeGraph.get_pois_for_city()` |
| `rate_pois(city, poi_list_json)` | Enriches with Foursquare ratings, filters low-quality, scores composite | `FoursquareRatingProvider.enrich_batch()` |
| `enrich_poi_details(poi_name, city)` | Wikipedia description + thumbnail image | `WikipediaFetcher.enrich()` |
| `estimate_visit_duration(category, subtype)` | Heuristic minutes per stop type | Built-in lookup table |
| `get_travel_time(lat1, lon1, lat2, lon2)` | Drive time estimate between stops | Haversine → 30 km/h urban |

### find_city_pois — KG-first design

The tool queries `RouteKnowledgeGraph.get_pois_for_city()` (in-memory, instant).
For Bay Area cities this always hits immediately. For cities outside the Bay Area,
`app.py` runs a **pre-flight** before the agent starts:

```
1. Check kg.known_cities() — is city already indexed?
2. If not → st.spinner("Fetching POIs for {city}...")
3. POIFinder.find_pois_in_bbox() → Overpass fetch (one-time, cached to disk)
4. kg.add_city_pois(city, lat, lon, pois) → adds City node + NEAR_POI edges
5. Agent starts → find_city_pois always hits KG (single clean path)
```

The tool itself has no fallback — KG is always warm before it runs.

---

## Ratings Layer (Foursquare Integration)

### Problem
OSM gives us POI locations and categories but no quality signal. Without ratings, all 80–150 POIs
in a city are equally ranked — the agent has no basis for "Golden Gate Park > random viewpoint."

### Solution: Foursquare Places API v3 + ChromaDB merge

```
OSM POIs (80–150)                    Foursquare batch results (≤150)
        │                                        │
        │                            3 API calls per city:
        │                            • search "park nature scenic outdoors" near {city}
        │                            • search "historic site monument" near {city}
        │                            • search "tourist attraction landmark" near {city}
        │                                        │
        │                            ┌───────────▼──────────────┐
        │                            │  ChromaDB ephemeral      │
        │                            │  collection              │
        │                            │  (Foursquare names       │
        │                            │   vectorized)            │
        │                            └───────────┬──────────────┘
        │                                        │
        └──────────────────────────► similarity search per OSM POI
                                                 │
                                     ┌───────────▼──────────────┐
                                     │  RatedPOI: OSM data +    │
                                     │  Foursquare rating (0–5) │
                                     │  + review count          │
                                     │  + review snippet        │
                                     │  + hours                 │
                                     └──────────────────────────┘
```

### Why ChromaDB for the merge (not fuzzy string matching)

Foursquare and OSM often name the same place differently:

| OSM name | Foursquare name |
|---|---|
| Alcatraz Island | Alcatraz |
| de Young Museum | de Young Fine Arts Museums of San Francisco |
| Angel Island State Park | Angel Island |

Character-level fuzzy matching (e.g. Levenshtein / rapidfuzz) fails here — the strings are too
different. Semantic similarity search via ChromaDB's default embedding model handles name variants,
abbreviations, and partial matches correctly, and reuses a dependency already in the project.

Fallback: if no name match scores below the distance threshold, haversine proximity ≤ 100 m
is checked as a final merge path.

### API call budget

| Scenario | Foursquare calls |
|---|---|
| First query for a new city | 3 (one per category) |
| Any repeat query (cached, 7-day TTL) | 0 |
| Full demo (5 Bay Area cities, pre-seeded) | 0 live calls |
| Daily free tier limit | 1000 |

### Composite ranking score

```
score = 0.4 × (rating / 5.0)
      + 0.3 × log(1 + review_count) / log(1 + 10000)
      + 0.3 × (0.1 if wikipedia_tag else 0.0)
```

POIs with `rating < 3.8` or `review_count < 20` are filtered out before scoring.

---

## Memory & Multi-turn Refinement

`MemorySaver` checkpoints the full `DayTripState` (messages + draft + approval status) after
every node. When the user types "remove museums, add more nature":

1. The Streamlit UI sends `Command(resume={"approved": False, "feedback": "remove museums..."})` 
2. The graph resumes from the `review` node, appends the feedback as a HumanMessage
3. Control returns to `plan` — the agent sees full prior context and re-plans

---

## Human-in-the-Loop Pattern

```python
def review(state: DayTripState):
    draft = state["draft_itinerary"]
    decision = interrupt(draft)       # graph pauses; Streamlit shows draft cards
    return {"approved": decision.get("approved", False)}
```

In Streamlit:
- Agent streams tool calls into an expander ("Agent is thinking…")
- When `__interrupt__` appears in the stream → extract draft JSON → render stop cards
- User clicks **Approve** → `graph.invoke(Command(resume={"approved": True}), config=...)`
- User types refinement → `graph.invoke(Command(resume={"approved": False, "feedback": text}), config=...)`

---

## Reuse from Week 2

| Week 2 component | How reused in Week 3 |
|---|---|
| `POIFinder` | `find_city_pois` tool wraps new `find_pois_in_bbox()` method |
| `WikipediaFetcher` | `enrich_poi_details` tool wraps `.enrich()` |
| `NarrativeChain` | `narrate` node calls it on the approved itinerary |
| `MapBuilder` | Renders final itinerary map |
| `LLMFactory` | Creates the `ChatAnthropic` instance injected into the agent |
| ChromaDB | Reused (ephemerally) for Foursquare name merge |
| `cache/pois/bay_area_all.json.gz` | `find_pois_in_bbox` hits master cache for Bay Area cities |

---

## Design Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Custom graph (not `create_react_agent` prebuilt) | Need clean interrupt point mid-graph; prebuilt runs to completion |
| 2 | `MemorySaver` checkpointer | Zero infrastructure; multi-turn refinement with full history |
| 3 | `interrupt()` in `review` node | User corrects draft before expensive narrative generation |
| 4 | Foursquare Places API v3 | Free tier (1000/day), global, returns ratings + snippets + hours |
| 5 | Batch 3 calls/city + **21-day cache** | Avoids 80-call/query naive approach; 21 days ensures cache outlives any evaluation/demo window |
| 6 | ChromaDB semantic merge for OSM↔Foursquare | Handles name variants; no new dependency (reuses existing ChromaDB) |
| 7 | `NullRatingProvider` fallback | Agent works without ratings; graceful degradation |
| 8 | Strategy pattern (`RATING_PROVIDER` env var) | One-line swap to Google Places or any future provider |
