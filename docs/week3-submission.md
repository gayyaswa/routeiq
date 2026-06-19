# RouteIQ — Week 3 Submission

## Project Overview

RouteIQ Week 3 adds a true agentic system on top of the Week 2 GraphRAG route planner: a **Day Trip Planner** powered by a LangGraph ReAct agent with human-in-the-loop review, a multi-source ratings layer, and dynamic knowledge graph expansion.

**The one-liner:**
My agent helps a traveler plan a full-day city itinerary in a Streamlit web app, replacing the 45-minute manual workflow of cross-referencing TripAdvisor, Google Maps, and Wikipedia. It finds OSM POIs, enriches them with ratings and visitor reviews, fetches Wikipedia facts, and schedules stops in road-time order autonomously using 5 tools — then pauses for human review before generating the narrative — and I'll know it works when a user can go from "Plan a day in San Francisco" to an approved, map-rendered itinerary with stop cards in under 60 seconds.

---

## What This Week Adds (Agent Layer)

| Property | Week 2 pipeline | Week 3 agent |
|---|---|---|
| Control flow | Fixed: parse → graph → rag → narrate | Dynamic: LLM decides which tools to call and in what order |
| Stop selection | Deterministic spatial join + scorer | LLM reasons about time budget, preferences, geographic variety |
| Multi-turn | One-shot | MemorySaver: "remove museums, add beaches" refines the same session |
| Human feedback | None | `interrupt_before=["review"]`: user approves or refines draft before narrative generates |
| Replanning | No | Agent loops back if user requests changes; full prior tool history preserved |

---

## Part 1: Agent Framework

### Agent Goal
Build a day-trip itinerary for a user-specified city using real OSM POI data, quality ratings, and Wikipedia facts — scheduled in road-time order — with a human review interrupt before the final narrative is written.

### Where it runs
Streamlit web app (Tab 1 — Day Trip Planner).

### Steps in order
1. Pre-flight: KG warm-up — check if city is already indexed; if not, Overpass fetch + `kg.add_city_pois()`.
2. Plan node (ReAct loop): `find_city_pois` → `rate_pois` → `enrich_poi_details` → `estimate_visit_duration` → structured Pydantic extraction → `_schedule_stops` (A* road routing).
3. Review node: `interrupt()` — graph pauses, Streamlit renders draft stop cards + map.
4. Human decides: Approve → narrate; Refine (free text) → plan (re-enters with feedback); Re-plan → full restart.
5. Narrate node: LLM generates 3–4 sentence trip narrative from approved itinerary + conversation history.

### Tools
| Tool | Type | Data source |
|---|---|---|
| `find_city_pois(city, categories)` | READ | OSM via `RouteKnowledgeGraph` (in-memory) |
| `rate_pois(city, poi_list_json)` | READ | `RatingsFactory` dispatcher — TripAdvisor and Foursquare adapters implemented; **current active provider: LLM Synthetic** (see Part 3) |
| `enrich_poi_details(poi_name, city)` | READ | Wikipedia MediaWiki API |
| `estimate_visit_duration(category, subtype)` | READ | Internal lookup table |
| `search_poi_by_name(name, city)` | READ | Nominatim geocoder (on refine only) |

All tools are READ-only. The only WRITE action is the approved itinerary rendered to Streamlit — no external state is modified.

### What it remembers
Full `DayTripState` (messages + draft itinerary + approval status) checkpointed by `MemorySaver` after every node. Each LangGraph thread is one planning session; state persists across plan→review→plan refinement loops within the session.

### What it must never do
- Invent POIs not returned by `find_city_pois`.
- Invent visitor quotes not found in `all_snippets` from the ratings tool.
- Invent Wikipedia facts not in the `enrich_poi_details` response.
- Calculate its own travel times between stops (road-based scheduling is handled in code by `_schedule_stops` after extraction).

### Human-in-the-loop
`interrupt_before=["review"]` pauses the graph after plan extraction. User sees draft stop cards and map. Free-text feedback re-enters the plan node with full conversation history appended as a `HumanMessage`. No narrative is generated until the user explicitly approves.

### Error handling
- `OverpassUnavailableError` in pre-flight: surfaced as `st.warning()`, agent does not start.
- Tool returns empty list: LLM falls back to available POIs and notes reduced selection.
- `GraphInterrupt` from `interrupt_before`: caught explicitly in Streamlit threads — this is the expected success signal, not an error.
- `NullRatingProvider` fallback: agent works without any ratings API key; POIs ranked by KG notability only.

### How I know it worked
User goes from empty form → approved stop cards with ratings, visitor reviews, and Wikipedia descriptions (+ thumbnail images) → map-rendered narrative in under 60 seconds for pre-seeded Bay Area cities.

The UI shows three live metrics after planning completes: **planning time**, **tool call count** (derived from `ToolMessage` instances in the LangGraph snapshot), and **stop count**. A typical SF run: 42 s · 22 tool calls · 8 stops.

LangSmith tracing is active (`LANGCHAIN_TRACING_V2=true`, project `routeiq-week3`). Every agent run produces a full trace in the LangSmith dashboard — tool call sequence, token usage per node, and latency breakdown — confirming the agent's reasoning path matches the expected ReAct pattern.

---

## Part 2: Architecture

```
User query (city · interests · hours · start time)
    │
    ▼  Pre-flight (app.py)
    │  kg.known_cities() → if new city: Overpass fetch → kg.add_city_pois()
    │
    ▼  LangGraph graph (MemorySaver checkpointer)
    │
    ├── plan node (ReAct loop)
    │     LLM + bind_tools(5 tools)
    │     while pending tool calls:
    │       execute tool → append ToolMessage
    │     → with_structured_output(DayTripItinerary)  [Pydantic validation]
    │     → _schedule_stops(A* road routing)           [code, not LLM]
    │
    ├── review node  ← interrupt_before
    │     interrupt(draft_itinerary)                    [graph pauses]
    │     Streamlit renders draft map + stop cards
    │     user: Approve / Refine / Re-plan
    │     Command(goto="narrate") or Command(goto="plan")
    │
    └── narrate node
          LLM generates 3–4 sentence trip narrative
          → Streamlit renders final map + cards + narrative
```

### Two-phase plan node (key design decision)

The plan node cannot use a single LLM call for both the ReAct loop and structured output extraction. `bind_tools()` enables free-form tool calling; `with_structured_output(DayTripItinerary)` enforces Pydantic validation. These modes conflict — the model cannot freely call tools while also being constrained to produce a specific JSON schema in the same call.

Solution: run them in sequence.
1. Phase 1 — `bind_tools`: LLM runs ReAct tool loop until no pending calls.
2. Phase 2 — `with_structured_output(DayTripItinerary)`: separate LLM call with full tool history as context → validated Pydantic itinerary.

### Knowledge Graph expansion (why it's architecturally important)

`find_city_pois` queries `RouteKnowledgeGraph.get_pois_for_city()` — always in-memory, always instant, no network call inside the agent. But the KG needs to have the city indexed first.

For cities outside the Bay Area pre-seed:
1. `app.py` checks `kg.known_cities()` before starting the agent.
2. If the city is missing: Overpass fetch → `kg.add_city_pois(city, lat, lon, pois)`.
3. `get_kg()` singleton ensures all tools share the same in-memory graph — dynamic expansion is visible to `find_city_pois` immediately.

Critical invariant: `find_city_pois` must call `get_kg()` (singleton), never `RouteKnowledgeGraph()` (new instance). A fresh instance would not contain the dynamically added city.

---

## Part 3: Datasets

| Source | What | Volume |
|--------|------|--------|
| OpenStreetMap via Overpass | POI metadata (name, lat/lon, OSM category/subtype, wikipedia tag) | Pre-seeded: 984 Bay Area POIs in `bay_area_all.json.gz`; any city on demand |
| Wikipedia MediaWiki API | Landmark intro text (≤500 chars) + thumbnail image URL | Fetched per POI by `enrich_poi_details` tool |
| LLM Synthetic (Claude) — **current active** | Claude-generated ratings, review snippets, and visitor quotes per POI | Disk-cached 21 days per city; active because live provider access is unavailable (see below) |
| TripAdvisor Content API — *implemented, inactive* | Ratings, up to 3 reviews (≥80 chars, sorted by HELPFUL), up to 5 photos | Adapter fully built in `routeiq/ratings/`; inactive — API key returned HTTP 403 (IAM deny) |
| Foursquare Places API — *implemented, inactive* | Ratings (0–10 → normalized 0–5), tips, hours | Adapter fully built; inactive — v3 endpoint retired (404), v2 lacks ratings on free tier |
| RouteKnowledgeGraph | 112+ nodes: POI, City, Region, Category; 4 typed edge types | Pre-seeded Bay Area; expanded on demand for new cities |

> **Current runtime configuration:** `RATING_PROVIDER=llm_synthetic`. TripAdvisor and Foursquare adapters are fully implemented and tested in `routeiq/ratings/`; switching either live is a one-env-var change once API access is granted.

### Ratings — composite score formula

```
score = 0.4 × (rating / 5.0)
      + 0.3 × log(1 + review_count) / log(1 + 10000)
      + 0.3 × (0.1 if wikipedia_tag else 0.0)
```

POIs with `rating < 3.8` AND `review_count < 20` are dropped before scoring. Top 30 returned to the LLM for final preference-based selection of 8–10 stops.

### Why three data sources

| Layer | Source | Provides | Why not replace with others? |
|---|---|---|---|
| Geographic | OSM (via KG) | All city POIs — complete, exact lat/lon, categories | TripAdvisor returns only ~50 "attractions" and misses parks, viewpoints, smaller historic sites |
| Social quality | TripAdvisor / Foursquare *(adapters implemented; LLM Synthetic currently active due to API access)* | Ratings, visitor reviews, and quotes | OSM has no quality signal — without ratings all 80–150 POIs rank equally |
| Factual knowledge | Wikipedia | Citable facts for `why_visit`, thumbnail image | Reviews are opinions; Wikipedia provides grounded facts |

---

## Part 4: Prompts

### Day Trip Planner system prompt (verbatim, active)

```
You are a day-trip itinerary planner. You build realistic, geographically ordered
itineraries for a single city using real POI data from tools.

Faithfulness rules — enforce strictly:
- visitor_quote: pick the single most vivid sentence from all_snippets; prefix with the
  review_source name (e.g. "Visitors on TripAdvisor say: '...'"). Never invent a quote.
- visitor_summary: write 1–2 sentences synthesizing the overall sentiment across all
  snippets in all_snippets. Ground every claim in the snippets — do not invent details.
- why_visit: one factual sentence sourced only from the POI's Wikipedia description.
  Never invent facts.
- activities: derive only from the Wikipedia description AND review snippets. Use the
  POI's OSM subtype as a last-resort fallback for one generic activity. Never invent activities.
- Schedule stops in geographic order to minimize travel time between them.
- Output ONLY the JSON block — no markdown fences, no commentary, no explanation.
```

**Design rationale:** Faithfulness rules are enumerated field-by-field because each field has a different source of truth. A single "don't hallucinate" instruction leaves the model guessing which field to ground in which source. Explicit per-field rules eliminate ambiguity.

---

### Day Trip Planner human prompt (verbatim, active)

```
Plan a {hours}-hour day trip in {city} starting at {start_time}.
Preferences: {preferences}

Tool call order:
1. find_city_pois — get POIs for the city
2. rate_pois — enrich with ratings and reviews; keep top candidates
3. enrich_poi_details — fetch Wikipedia context for the top 8 POIs
4. estimate_visit_duration — get visit duration per stop subtype

Your job is to SELECT the best 8–10 stops that match the preferences and variety of
experience. Do NOT try to calculate travel times or fit stops within the time budget
yourself — road-based scheduling is handled automatically after you output the itinerary.
Set arrival_time and departure_time to placeholder values ("TBD"); they will be replaced.

Output format (JSON only, no fences):
{
  "city": "{city}",
  "date": "today",
  "total_hours": {hours},
  "stops": [
    {
      "order": 1,
      "name": "<POI name>",
      "category": "<OSM category>",
      "lat": 0.0, "lon": 0.0,
      "arrival_time": "TBD", "departure_time": "TBD",
      "visit_duration_min": 90,
      "why_visit": "<one factual Wikipedia sentence>",
      "visitor_quote": "<review_source>: '<single most vivid snippet from all_snippets>'",
      "visitor_summary": "<1-2 sentence synthesis of overall sentiment from all_snippets>",
      "activities": ["<activity 1>", "<activity 2>"],
      "rating": 4.5, "review_count": 1200,
      "review_source": "<TripAdvisor | Foursquare | Unknown>",
      "photo_urls": ["<url1>", "<url2>"],
      "image_url": "<Wikipedia thumbnail fallback>",
      "hours": "<opening hours string or null>"
    }
  ],
  "narrative": null
}
```

**Key design note:** "Set arrival_time and departure_time to placeholder values ('TBD'); they will be replaced" is the most important instruction. Without it, the LLM either tries to calculate road travel times itself (and fails) or leaves times at `null`, crashing the Pydantic validator. Separating LLM selection from code-based scheduling was the fix.

---

### Route Planner narrative prompt evolution (carried from Week 2)

Three generations — the Week 2 narrative prompt is included for continuity:

**V1 — hallucinated visit reasons (no description context)**
**V2 — Wikipedia-enriched: grounded in real landmark text**
**V3 — KG-enriched (active): city + region + nearby stops added**

```
Generate a scenic route narrative for the following trip.

Origin: {origin}
Destination: {destination}
Total distance: {distance_km} km
Estimated drive time: {drive_time_min} minutes

Recommended stops (graph-verified: spatially on route, Wikipedia-enriched):
{poi_context}

Each stop is formatted as:
  name | category | city | region | nearby stops | description excerpt

Instructions:
- Write an engaging opening narrative (3-5 sentences) that captures the character
  of the route and region.
- List each stop: name | detour time | one sentence why to visit, drawn from the description.
- Mention the region where it adds flavour (e.g. "deep in the Hill Country").
- Ground every fact in the provided context. Do not invent locations or distances.
```

---

## Part 5: Iterations

### 1. LLM tried to calculate travel times
**Problem:** The agent was given the full output schema including `arrival_time` and `departure_time`. The LLM tried to calculate road travel times itself, producing wildly inaccurate schedules (20 minutes to cross San Francisco).
**Fix:** Added explicit instruction "Do NOT try to calculate travel times — road-based scheduling is handled automatically after you output the itinerary. Set arrival_time and departure_time to 'TBD'." `_schedule_stops()` in code runs A* routing after Pydantic extraction and fills in real road times.
**Learning:** Don't ask the LLM to do what code does better. Separate LLM judgment (which stops to include) from deterministic computation (road-time scheduling).

### 2. `interrupt_before` vs `interrupt()` inside the node
**Problem:** Using `interrupt_before=["review"]` raises `GraphInterrupt` when the plan node transitions to the review node. Streamlit threads caught this as an unhandled exception, causing the "first-run no draft" symptom.
**Fix:** Caught `GraphInterrupt` explicitly in both `_run_dt_planning_thread` and `_run_dt_refine_thread` as the expected success signal — not an error.
**Learning:** LangGraph's `interrupt_before` is a first-class control flow mechanism, not an exception in the traditional sense. All callers of `graph.stream()` need to expect and handle `GraphInterrupt`.

### 3. `get_kg()` singleton vs `RouteKnowledgeGraph()` new instance
**Problem:** `find_city_pois` tool was instantiating `RouteKnowledgeGraph()` directly. Pre-flight in `app.py` called `get_kg().add_city_pois()` on the singleton. The tool saw a fresh instance with no dynamically added cities — always returning empty POI lists for out-of-area cities.
**Fix:** `find_city_pois` calls `get_kg()` (singleton function, returns the process-wide shared instance).
**Learning:** In a multi-component system with shared in-memory state, the singleton pattern must be enforced everywhere. One caller using `new Instance()` breaks the invariant silently.

### 4. `ox.geocode("Oakland, CA")` → Canada
**Problem:** Nominatim resolved "Oakland, CA" to Oakland, Ontario, Canada. The route bbox was in Canada, no Bay Area POIs fell within it, and the agent returned an empty itinerary.
**Fix:** `_schedule_stops` uses the stop centroid derived from A* routing (already in the Bay Area) as the bbox anchor, not `ox.geocode(city)`.
**Learning:** Nominatim abbreviation handling is inconsistent — "CA" can resolve to California or Canada depending on query phrasing. Never geocode by city name when you already have coordinates from another source.

### 5. OSM→provider name matching via ChromaDB
**Problem:** String matching between OSM names ("de Young Museum") and TripAdvisor names ("de Young Fine Arts Museums of San Francisco") failed for ~40% of POI pairs.
**Fix:** ChromaDB embedding similarity for the initial merge pass; haversine proximity ≤100 m as a fallback for cases where names are completely different.
**Learning:** Name matching across geospatial data sources is an entity resolution problem, not a string comparison problem. Semantic embeddings handle abbreviations and partial names naturally. Reusing ChromaDB (already a project dependency) kept the solution simple.
**Note:** This matching logic is exercised when TripAdvisor or Foursquare is the active provider. With `LLMSyntheticRatingProvider` (current active), POI names are passed directly to the LLM — no cross-source name resolution is needed.

### 6. TripAdvisor key 403 IAM deny
**Problem:** TripAdvisor Content API returned HTTP 403 for the live API key. The ratings layer had no fallback.
**Fix:** Added `LLMSyntheticRatingProvider` — Claude generates realistic ratings, snippets, and visitor quotes for any city, disk-cached with a 21-day TTL. Strategy pattern means it's a one-env-var swap (`RATING_PROVIDER=llm_synthetic`).
**Learning:** External API keys fail in production. The Strategy pattern with a graceful fallback provider is not nice-to-have — it's essential for demo reliability.

### 7. Foursquare v3 `/nearby` endpoint retired
**Problem:** Foursquare's documented v3 endpoint returned HTTP 404. The adapter was built against docs that described a deprecated endpoint.
**Fix:** Switched to Foursquare v2 (`api.foursquare.com/v2/venues/search`). v2 doesn't include ratings on the free tier, so Foursquare became the secondary provider.
**Learning:** API documentation doesn't always reflect which version is actually live. Check response codes against a live API call before building an adapter, not just the docs.

---

## Part 6: Reuse from Week 2

| Week 2 component | How reused in Week 3 |
|---|---|
| `POIFinder` | Pre-flight `find_pois_in_bbox()` for out-of-area cities |
| `WikipediaFetcher` | `enrich_poi_details` tool wraps `.enrich()` |
| `RouteKnowledgeGraph` + `get_kg()` | `find_city_pois` tool + `add_city_pois()` for dynamic KG expansion |
| `MapBuilder` | Renders final itinerary Folium map (AntPath route + numbered markers) |
| `LLMFactory` | `create_llm()` injected into all AI components — swappable Anthropic/Nebius |
| ChromaDB | Reused ephemerally for OSM↔provider name merge in `rate_pois` |
| `cache/pois/bay_area_all.json.gz` | Cache hit in `find_pois_in_bbox` for all Bay Area cities — zero Overpass calls in demo |

---

## Part 7: Key Learnings

### 1. Separate LLM judgment from deterministic computation
The agent is good at selecting which stops to visit and why. It is bad at computing road travel times. Asking it to do both produced inaccurate schedules. The correct split: LLM selects and ranks stops → code handles scheduling. This generalizes: wherever you have a deterministic algorithm that produces a correct answer, don't ask the LLM to replicate it.

### 2. `interrupt_before` is control flow, not an error
LangGraph's `interrupt_before` pauses the graph at a node boundary. The resulting `GraphInterrupt` is the expected success signal — not an exception to be suppressed. Every caller of `graph.stream()` must handle it explicitly. Treating it as an unexpected error was the root cause of the first-run draft bug.

### 3. Singleton patterns must be enforced everywhere
In a multi-component system with shared in-memory state, one caller using `new Instance()` instead of `get_singleton()` silently breaks the state invariant. The bug where `find_city_pois` created a fresh KG instance — missing all dynamically added cities — was invisible until a non-Bay-Area city was tested. Guard singleton access at the module boundary, not just at initialization.

### 4. Strategy pattern for external providers is essential
Three providers (TripAdvisor, Foursquare, LLM synthetic) were tried, and each failed in a different way (403 IAM deny, retired endpoint, hallucination risk without disk cache). The Strategy pattern with `POIRatingProvider` ABC meant each failure was handled by swapping one env var — no code changes, no broken demos. Without it, each provider failure would have required a refactor of the ratings layer.

### 5. Entity resolution across geospatial data sources is non-trivial
OSM names and provider names for the same physical location can be semantically identical but lexically different ("de Young Museum" vs "de Young Fine Arts Museums of San Francisco"). String matching fails; embedding similarity handles it naturally. When two systems need to match the same entity by name, treat it as an entity resolution problem, not a string comparison.

### 6. External API dependencies break at demo time
TripAdvisor (403), Foursquare (404 on v3). Two of three planned providers failed before a single demo query ran. The lesson: always build the synthetic/mock fallback before connecting the live API, so the system is demo-ready before the key activates.

### 7. Graceful pre-flight beats graceful degradation inside the agent
Checking `kg.known_cities()` and running the Overpass fetch before the agent starts (with a Streamlit spinner) is far better UX than having the agent fail mid-tool-call because the KG is empty. Pre-flight is the pattern: validate dependencies before handing control to the agent, not during.

### 8. Observability is how you verify an agent actually did what you think
The ReAct loop runs inside a background thread. Without tracing, there's no way to know which tool was called when, what it returned, or which LLM call consumed most of the latency. LangSmith (`LANGCHAIN_TRACING_V2=true`) solved this: every planning run produces a trace with the full tool call sequence, token counts per node, and per-step latency. This revealed that `enrich_poi_details` accounts for ~60% of planning time (one Wikipedia API call per POI candidate, executed serially) and that the LLM consistently calls it for 10–12 candidates before settling on 8 stops. That's not visible from the UI alone — you only see the end result, not the reasoning path.

---

## Part 8: Tech Stack

| Component | Tool | Purpose |
|---|---|---|
| Agent framework | LangGraph (StateGraph + MemorySaver) | ReAct loop + human-in-the-loop interrupt + multi-turn state |
| LLM | Claude Sonnet 4.6 via LangChain | Plan node (ReAct + structured extraction) + narrate node |
| LLM alternative | Nebius Token Factory (OpenAI-compatible) | Dev/testing; `LLM_PROVIDER=nebius` env var swap |
| Road network | OSMnx + NetworkX | A* pathfinding for stop scheduling |
| POI data | OpenStreetMap via Overpass | Geographic completeness for any city |
| Ratings — **current active** | LLM Synthetic (Claude) | Generates ratings, review snippets, and visitor quotes per POI; disk-cached 21 days |
| Ratings — TripAdvisor *(implemented)* | TripAdvisor Content API | Adapter complete; inactive — API key returned HTTP 403 |
| Ratings — Foursquare *(implemented)* | Foursquare v2 | Adapter complete; inactive — v3 retired, v2 lacks ratings on free tier |
| Knowledge graph | NetworkX DiGraph + `get_kg()` singleton | POI/City/Region typed edges; dynamic expansion |
| Name matching | ChromaDB (ephemeral) | OSM↔provider name entity resolution |
| Map rendering | Folium + AntPath | Animated route + numbered markers |
| UI | Streamlit | Two-tab app; background threads for agent streaming |
| Observability | LangSmith (`routeiq-week3` project) | Full agent traces: tool call sequence, token usage per node, per-step latency |
| Testing | pytest | 213 tests across 22 files |
