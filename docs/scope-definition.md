# RouteIQ — Scope Definition (Week 3)

## Problem Statement

Travelers planning a city day trip have no single tool that enforces **both geographic constraints and editorial quality simultaneously**. Generic search returns popular results scattered across a city. Vector-only AI search surfaces semantically relevant stops that may be miles apart or outside the city. Human travel blogs are curated but not personalized to a time budget or preference.

RouteIQ's Day Trip Planner answers: *"What should I do today in this city, given my interests and how many hours I have?"* — using an AI agent that selects and schedules real, high-quality stops, then pauses for human approval before finalizing.

## Target User

A traveler arriving in a city who wants 4–8 specific, high-quality stops scheduled into a realistic day — not a wall of results to sort through themselves.

---

## In Scope (Week 3 — Day Trip Planner)

### Day Trip Planner (primary Week 3 deliverable)
- Natural-language city queries: "Plan a scenic day in San Francisco — history and nature, 8 hours"
- LangGraph agent: `plan` node (ReAct tool loop) → `review` node (human-in-the-loop interrupt) → `narrate` node
- 5 tools: `find_city_pois`, `rate_pois`, `enrich_poi_details`, `get_travel_time`, `estimate_visit_duration`
- TripAdvisor integration: real ratings (1–5), top 3 most-helpful reviews (≥80 chars), up to 5 photos per stop
- Foursquare as swappable secondary provider (`RATING_PROVIDER=foursquare`)
- Stop cards with 4 grounded fields: `why_visit` (Wikipedia only), `visitor_quote` (verbatim best snippet), `visitor_summary` (LLM synthesis across all snippets), `activities` (Wikipedia + review snippets only — never invented)
- Human approval loop: user reviews draft → approves or refines with free-text feedback → agent re-plans
- Post-approval: 3–4 sentence narrative + numbered Folium map

### Route Planner (unchanged from Week 2 scope)
Graph RAG scenic route planner: OSM road network + A\* pathfinding + Wikipedia enrichment + vector baseline comparison. See Week 2 scope definition.

---

## Out of Scope

| Area | Reason excluded |
|---|---|
| Real-time traffic / incidents | Live data infrastructure out of proportion to the demo value |
| Turn-by-turn navigation | RouteIQ focuses on *what* to see, not *how* to drive |
| Saved routes / user accounts | Auth + persistence are a deployment concern, not a retrieval problem |
| Multi-day trip planning | Accommodation logic is out of scope; the single day is the unit of value |
| Neo4j / persistent graph DB | In-memory NetworkX + ChromaDB covers demo scale |
| Review aggregation across providers simultaneously | Single-source traceability is a deliberate design choice — mixing sources makes attribution ambiguous |
| Mobile app | Web-only Streamlit UI for the submission window |

---

## What a Good Day Trip Stop Needs — and Why the Architecture Serves It

A stop earns a place on the itinerary only when it satisfies five constraints simultaneously. Each constraint is enforced by a different layer of the system:

| User need | Constraint | Enforced by |
|---|---|---|
| "In the city I'm visiting" | Geographic completeness | `RouteKnowledgeGraph.get_pois_for_city()` pulls **all** OSM-verified POIs for the city — not just semantically similar ones. A great museum is never missed because the query was "parks." |
| "Worth visiting, not just nearby" | Editorial quality | TripAdvisor ratings (1–5) + helpful review snippets filter for stops that real visitors praise. Low-rated stops (< 3.8) with few reviews are dropped. |
| "Fits in my day" | Temporal feasibility | `estimate_visit_duration` and `get_travel_time` tools build a time-realistic schedule. The LLM reasons over the resulting time slots. |
| "Matches what I like" | Preference alignment | The agent uses NL preference strings ("history", "nature") in its LLM reasoning — not hard OSM category filters — so it can handle nuanced interests. |
| "I want final say" | Human agency | `interrupt_before=["review"]` pauses the agent after the draft is produced. The user approves or provides feedback; the agent re-plans with full conversation history. |

**Why not pure vector search?** Vector search returns stops similar to the query but ignores geography (#1) and time (#3). A query for "historic sites in San Francisco" might surface Alcatraz (correct) alongside Gettysburg (semantically similar, geographically wrong). The Knowledge Graph enforces city boundaries; vector search cannot.

**Why not a static pipeline?** A static pipeline (like the Route Planner) has no approval step. The Day Trip Planner is inherently interactive — the user's first reaction to the draft is informative. The interrupt pattern converts that reaction into a concrete refinement signal rather than discarding it.

---

## Advanced Agentic Design Choices (Bonus Patterns)

### Human-in-the-Loop Interrupt
`interrupt_before=["review"]` pauses the agent for explicit user approval after the planning phase. Free-text feedback is appended as a `HumanMessage` to the state, and the agent re-enters `plan` without losing tool call history. This is the canonical LangGraph pattern for approval workflows — not a workaround.

### Structured LLM Output (Pydantic)
Two-phase output: the ReAct loop uses `bind_tools()` for tool calling; a second LLM call uses `with_structured_output(DayTripItinerary)` (Pydantic) to extract the validated itinerary. This guarantees all stop fields are present and typed correctly regardless of the LLM's tool-loop formatting.

### TripAdvisor + Foursquare as Swappable Single-Source Providers
Both providers implement the `POIRatingProvider` Strategy ABC. The `source_name` abstract property propagates to every `RatedPOI.review_source` field, ensuring the UI badge and `visitor_quote` prefix always reflect the active provider. Swapping is a single env var change (`RATING_PROVIDER=tripadvisor` ↔ `foursquare`). Single-source traceability is deliberate: the agent never mixes review sources across stops in the same itinerary.
