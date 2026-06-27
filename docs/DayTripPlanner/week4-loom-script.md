# Week 4 Loom Script (~5 min)

**Format:** Screen share the GDoc, scroll through each section as you talk.

---

## Section 1 — New features added this week (0:00–0:50)

"This week I added activity-based day trip planning to RouteIQ. Previously the agent could plan a scenic day trip in any city — but if you said 'I want to go hiking', it would return generic scenic stops, not actual hiking trails. The core addition is a new tool called `select_pois_for_day`. When the user specifies an activity, this tool runs a classifier over the POI pool and splits results into two tracks — Track 1 is activity-matched stops, Track 2 fills remaining slots with scenic picks. There are two classifiers: an OSM tag-based one that works offline, and a Tavily web-search classifier that catches POIs with ambiguous tags like parks and picnic areas."

---

## Section 2 — Metrics (0:50–1:40)

"I evaluated four metrics. M1 is tool routing accuracy — did the agent call the right tool first? Activities present means it must call `select_pois_for_day`, not `find_city_pois`. M2 is activity recall — what fraction of requested activities actually appear in the itinerary. M3 is match quality, scored 1 to 5 by an LLM judge: 1 is unrelated, 3 is a reasonable stretch, 5 is clearly designed for the activity. And M4 is plan time — end to end under 90 seconds p95. Pass bars are: routing 100%, recall 70% or above, match quality 3.5 or above, time under 90 seconds."

---

## Section 3 — Baseline run and failure analysis (1:40–2:40)

"I ran a 3-query sanity check across all 5 classifier-and-ratings configurations. M1 routing was already 100% — I had fixed the agent's iteration-zero recovery nudge before this run. But M2 recall failed in three of five configs — the biking query returned zero recall. Tracing the tool call revealed five data pipeline bugs: OSM subtypes were being dropped in the knowledge graph loader, so the classifier had nothing to match against. A legacy Wikipedia filter was cutting 94% of the POI pool. The Tavily classifier was only looking at the first 40 POI names. The activity slot budget was fixed at one regardless of pool size. And the NYC rating call was sending 900 POIs in one batch, hitting the context limit. M4 latency also failed in the Tavily configs — cold cache runs were hitting 98 to 500 seconds."

---

## Section 4 — Improvement fixes (2:40–3:30)

"Nine improvements across four levers. Control flow: the iter-zero nudge now branches on whether activities are set — with activities it names `select_pois_for_day` explicitly. Data pipeline: subtype passthrough added to both city loaders, Wikipedia filter removed, Tavily name cap lifted, slot budget made proportional to pool size, NYC batching chunked to 50 POIs. And caching: Tavily LLM name extraction is now cached write-through — that took the tool from 50 seconds cold to under 2 seconds warm. Wikipedia descriptions also cached. And the prompt now explicitly tells the LLM not to call `estimate_visit_duration` or `enrich_poi_details` since `rate_pois` already returns that data — which cut the ReAct loop from 12 iterations down to 2 or 3."

---

## Section 5 — Post-improvement results (3:30–4:20)

"Full smoke test: 15 queries across SF and NYC, all 5 configs. Routing accuracy hit 100% in every single configuration. Recall ranged from 83% on the OSM config up to 100% on Tavily plus LLM-Synthetic. The Tavily classifier is the biggest single lever — plus 17 percentage points over OSM — because it finds parks and picnic areas through web content even when OSM tags are missing. For enrichment, LLM-Synthetic covers 87% of stops with ratings but those are fabricated. TripAdvisor covers only 35% but they're real ratings with real photos. My recommended config is Tavily plus TripAdvisor — 15 out of 15, 97% recall, 43 seconds average, real photos on 38% of stops."

---

## Section 6 — Future work (4:20–5:00)

"Three gaps the eval exposed that no current config solves well. Photos: even the best config only has photos on 38% of stops — TripAdvisor misses trails and viewpoints entirely. Fix is a Wikimedia Commons geo-image fallback. Multi-activity recall hits a ceiling at 50% for queries with two or more activities — that's a slot budget logic fix, one line of code. And picnic recall is zero in OSM configs because the OSM fetcher doesn't load leisure tags — again a one-line category addition. The next eval run is the edge-case block, Q16 to Q30, but I've intentionally scoped that for after these fixes are in place so the results measure progress rather than just confirming known failures."

---

## Key numbers to have on screen

- Routing: 15/15 (100%) across all 5 configs
- Recall: 83% (OSM) → 100% (Tavily+Synth), +17% lift
- ReAct iterations: 12 → 2–3
- Plan time: ~226s → ~30s (warm cache)
- Test suite: 315/315 passing
- Improvements: 9 total
