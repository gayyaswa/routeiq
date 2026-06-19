# RouteIQ — Demo Script (≤5 min)

> **Speaking pace:** ~150 words/min. This script is ~700 spoken words — roughly 4:40. Pause at each [ACTION] to let the UI catch up before continuing.

---

## [0:00 – 0:30] Hook

Hi — I'm going to show you RouteIQ, an agentic day-trip planner I built for Week 3.

The core idea: instead of spending 45 minutes cross-referencing Google Maps, TripAdvisor, and Wikipedia, you type a city, pick your interests, and a LangGraph ReAct agent figures out the best stops, enriches them with ratings and Wikipedia facts, and hands you a map-rendered itinerary — pausing to ask for your approval before it commits to the final narrative.

Let me show you exactly how that works, and then I'll pull back the curtain on two things I think make this technically interesting: how the agent calls tools autonomously, and how we guarantee the schedule times are actually correct.

---

## [0:30 – 1:15] Input and pre-flight

[ACTION: Show Tab 1 — Day Trip Planner. City = "San Francisco, CA", interests = nature + history, 8 hours, start 9:00 AM. Hit Plan My Day.]

The moment I click Plan, two things happen before the agent even starts.

First, a pre-flight check: the app looks at the in-memory knowledge graph and asks "is San Francisco already indexed?" For Bay Area cities it is — 984 POIs loaded from a local OSM cache. No Overpass network call needed. For a new city like Austin or Seattle, it would do that Overpass fetch here, with a spinner, so the agent never has to wait for data mid-run.

Second, the LangGraph graph starts with a clean `DayTripState`. That state has eight fields: the conversation messages, city, preferences, time budget, start time, a `draft_itinerary` slot, a `route_coords` slot, an `approved` flag, and a `narrative` slot. Everything is null or empty except what we just typed. Let's watch the graph fill it in.

---

## [1:15 – 2:30] Tool calling — the ReAct loop

[ACTION: Watch the progress stepper: "Finding POIs → Rating POIs → Enriching details → Structuring itinerary".]

The agent enters the **plan node**. The LLM has five tools bound to it and a suggested order in the prompt — but what drives the actual sequence is data availability, not a fixed script. After every tool call, the LLM looks at what's now in the conversation and asks: what am I still missing to build a complete itinerary?

Here's how that plays out:

**Iteration 1 — `find_city_pois`**: The LLM has nothing yet. It calls this first because without a POI list there's nothing to rate, enrich, or schedule. Returns up to 100 POIs from the in-memory knowledge graph — each with name, lat/lon from OSM, category, and subtype. The LLM didn't generate those coordinates; they came from OpenStreetMap. That matters — I'll come back to it.

**Iteration 2 — `rate_pois`**: Now the LLM has POIs but no quality signal — all 100 rank equally. It calls `rate_pois` with that list. The active provider right now is an LLM-synthetic ratings layer — we built TripAdvisor and Foursquare adapters fully, but both hit API access issues. The synthetic provider generates realistic ratings and review snippets, disk-cached 21 days. The tool applies a composite score — 40% rating, 30% review volume, 30% Wikipedia significance — and returns the top 30. Now the LLM has quality scores but no factual context per POI.

**Iterations 3–10 — `enrich_poi_details`**: Called once per top POI. Each call hits the Wikipedia MediaWiki API and returns a description excerpt and thumbnail URL. The LLM calls this in a loop — one POI per iteration — because each call fills in a `why_visit` fact it couldn't otherwise ground. Once all 8 target POIs have descriptions, it stops calling this tool.

**Final iteration — `estimate_visit_duration`**: The LLM now has POIs, ratings, and Wikipedia facts. The last missing piece is how long to spend at each stop. It calls this tool per OSM subtype — museum → 90 min, viewpoint → 30 min — to fill in `visit_duration_min`.

At that point the LLM's response contains no tool calls at all. That's the real exit condition — the loop breaks because there's nothing left to look up. The 12-iteration cap is purely a safety guard in case a confused model keeps requesting tools indefinitely; in a normal run you exit naturally around iteration 8–11.

Then a **second LLM call** with `with_structured_output` extracts a validated Pydantic model from all those tool results. These two phases must be separate: you can't bind free-form tools and enforce a strict JSON schema in the same call.

---

## [2:30 – 3:30] Anti-hallucination — how we keep the LLM honest

[ACTION: Show a stop card — point to the visitor quote, the why_visit line, the rating.]

Every field in the output has an explicit source-of-truth rule enforced in the extraction prompt:

- **`why_visit`** — one factual sentence from the Wikipedia description only. The prompt says: "Never invent facts."
- **`visitor_quote`** — must be the single most vivid sentence from the `all_snippets` array returned by `rate_pois`. Prefixed with the review source name. Never invented.
- **`visitor_summary`** — synthesised only from those same snippets.
- **`lat`, `lon`, `rating`, `review_count`, `photo_urls`, `hours`** — the prompt says: "Copy these EXACTLY from the tool output — do not invent or modify."

The Pydantic schema is a second line of defense: if the LLM tries to invent a float where a string should be, or omits a required field, the extraction raises a validation error and we retry once.

The biggest hallucination risk was travel times — the LLM would try to calculate "20 minutes from the Golden Gate Bridge to Alcatraz" and just make it up. The fix: the prompt tells the agent to set `arrival_time` and `departure_time` to the literal string `"TBD"`. Then we throw those values away and replace them with real ones.

---

## [3:30 – 4:15] A* scheduling — real road times, not guesses

[ACTION: Show the final stop cards with arrival/departure times filled in. Point to the timeline.]

After the Pydantic extraction, `_schedule_stops` runs entirely in Python — no LLM involved.

Step one: sort the stops by nearest-neighbor. Start from the highest-rated stop, then always pick the geographically closest unvisited stop next. This minimises total driving without solving the full TSP.

Step two: for each consecutive pair, call `RouteGraph.find_route()`. Under the hood that's `nx.astar_path()` on a NetworkX MultiDiGraph loaded from OSM via OSMnx — using haversine distance as the A* heuristic, with road length as the edge weight. The result is a sequence of real road nodes. We sum their lengths in metres, divide by average city speed of 50 km/h, and add 7 minutes of transition overhead — parking and walking to the entrance.

The first stop gets `arrival_time = start_time`. Each subsequent stop gets `arrival_time = previous departure + road travel time`. Then we trim from the tail: if the last stop's departure time overshoots the time budget, it gets dropped.

What you see on the card — "9:00 AM to 10:30 AM at the de Young Museum, then 10:47 AM at Golden Gate Park" — is derived from actual road network geometry, not a language model's estimate.

---

## [4:15 – 4:50] Human-in-the-loop and wrap-up

[ACTION: Show the draft stop cards. Click "Approve". Show the narrative appear.]

The graph pauses before generating the narrative and waits for the user. That's a LangGraph `interrupt_before` on the review node — a first-class control flow mechanism. If I type "swap the museum for a beach," the agent re-enters the plan node with my feedback appended to the conversation history, all prior tool results still in context.

Once I approve, the narrate node generates a 3–4 sentence trip description grounded in the approved itinerary.

So the full stack: OSM for geographic completeness, LLM for preference-aware stop selection, Wikipedia for citable facts, composite scoring for quality filtering, and A* routing for honest times — with the human kept in the loop before anything is committed.

Thanks.

---

## Screen checklist (before recording)

- [ ] `streamlit run app.py` running locally
- [ ] City pre-set to "San Francisco, CA", interests: nature + history, 8 h, 9:00 AM
- [ ] Terminal hidden (or split-screened to show tool call logs if desired)
- [ ] Browser zoom at 125% so text is readable in recording
- [ ] Record at 1080p; trim silence at start/end
