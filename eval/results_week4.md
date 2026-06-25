# RouteIQ Week 4 Activity Eval

*Generated 2026-06-25 00:24*

## Run 1 — OSM + LLM-Synthetic (baseline)

| # | City | Activities | Stops | Recall | Routing | Tools | Time | Pass/Fail |
|---|------|------------|-------|--------|---------|-------|------|-----------|
| 1 | San Francisco, CA | hiking | 8 | 100% | PASS (select_pois_for_day) | 2 | 56.0s | PASS |
| 2 | San Francisco, CA | biking | 7 | 100% | PASS (select_pois_for_day) | 9 | 75.1s | PASS |
| 3 | San Francisco, CA | kids | 5 | 100% | PASS (select_pois_for_day) | 2 | 44.0s | PASS |
| 4 | San Francisco, CA | swimming | 6 | 100% | PASS (select_pois_for_day) | 2 | 33.2s | PASS |
| 5 | San Francisco, CA | kayaking | 8 | 100% | PASS (select_pois_for_day) | 6 | 44.3s | PASS |
| 6 | San Francisco, CA | picnic | 6 | 0% | PASS (select_pois_for_day) | 2 | 29.0s | FAIL |
| 7 | San Francisco, CA | hiking, biking | 8 | 50% | PASS (select_pois_for_day) | 2 | 44.3s | PASS |
| 8 | San Francisco, CA | swimming, kids | 6 | 100% | PASS (select_pois_for_day) | 2 | 37.6s | PASS |
| 9 | New York City, NY | hiking | 7 | 100% | PASS (select_pois_for_day) | 3 | 88.1s | PASS |
| 10 | New York City, NY | biking | 5 | 100% | PASS (select_pois_for_day) | 2 | 105.4s | PASS |
| 11 | New York City, NY | kids | 8 | 100% | PASS (select_pois_for_day) | 2 | 43.5s | PASS |
| 12 | New York City, NY | kayaking | 6 | 100% | PASS (select_pois_for_day) | 2 | 45.1s | PASS |
| 13 | New York City, NY | picnic | 5 | 0% | PASS (select_pois_for_day) | 3 | 41.2s | FAIL |
| 14 | New York City, NY | hiking, biking | 7 | 100% | PASS (select_pois_for_day) | 2 | 36.2s | PASS |
| 15 | New York City, NY | swimming, kids | 7 | 100% | PASS (select_pois_for_day) | 2 | 266.6s | PASS |

**Run 1 — OSM + LLM-Synthetic (baseline)**  
Pass rate: 13/15  
Tool routing accuracy: 15/15  
Avg activity recall: 83%  
Avg plan time: 66.0s  
Enrichment — %rated: 87% | %with reviews: 87% | %with photos: 0% | avg rating: 4.27  
Match quality — %with evidence: 67% | avg match score: 3.72/5  


## Run 2 — Tavily classifier + LLM-Synthetic

| # | City | Activities | Stops | Recall | Routing | Tools | Time | Pass/Fail |
|---|------|------------|-------|--------|---------|-------|------|-----------|
| 1 | San Francisco, CA | hiking | 8 | 100% | PASS (select_pois_for_day) | 2 | 136.3s | PASS |
| 2 | San Francisco, CA | biking | 7 | 100% | PASS (select_pois_for_day) | 2 | 39.3s | PASS |
| 3 | San Francisco, CA | kids | 7 | 100% | PASS (select_pois_for_day) | 3 | 48.1s | PASS |
| 4 | San Francisco, CA | swimming | 6 | 100% | PASS (select_pois_for_day) | 6 | 61.2s | PASS |
| 5 | San Francisco, CA | kayaking | 8 | 100% | PASS (select_pois_for_day) | 7 | 88.1s | PASS |
| 6 | San Francisco, CA | picnic | 6 | 100% | PASS (select_pois_for_day) | 2 | 44.1s | PASS |
| 7 | San Francisco, CA | hiking, biking | 8 | 100% | PASS (select_pois_for_day) | 2 | 48.1s | PASS |
| 8 | San Francisco, CA | swimming, kids | 5 | 100% | PASS (select_pois_for_day) | 2 | 49.6s | PASS |
| 9 | New York City, NY | hiking | 9 | 100% | PASS (select_pois_for_day) | 2 | 37.8s | PASS |
| 10 | New York City, NY | biking | 5 | 100% | PASS (select_pois_for_day) | 2 | 58.7s | PASS |
| 11 | New York City, NY | kids | 6 | 100% | PASS (select_pois_for_day) | 3 | 278.9s | PASS |
| 12 | New York City, NY | kayaking | 6 | 100% | PASS (select_pois_for_day) | 3 | 46.1s | PASS |
| 13 | New York City, NY | picnic | 4 | 100% | PASS (select_pois_for_day) | 3 | 47.8s | PASS |
| 14 | New York City, NY | hiking, biking | 7 | 100% | PASS (select_pois_for_day) | 2 | 34.7s | PASS |
| 15 | New York City, NY | swimming, kids | 6 | 100% | PASS (select_pois_for_day) | 2 | 36.4s | PASS |

**Run 2 — Tavily classifier + LLM-Synthetic**  
Pass rate: 15/15  
Tool routing accuracy: 15/15  
Avg activity recall: 100%  
Avg plan time: 70.3s  
Enrichment — %rated: 86% | %with reviews: 86% | %with photos: 0% | avg rating: 4.33  
Match quality — %with evidence: 80% | avg match score: 3.64/5  


## Run 3 — Tavily classifier + Tavily enrichment

| # | City | Activities | Stops | Recall | Routing | Tools | Time | Pass/Fail |
|---|------|------------|-------|--------|---------|-------|------|-----------|
| 1 | San Francisco, CA | hiking | 8 | 100% | PASS (select_pois_for_day) | 2 | 45.0s | PASS |
| 2 | San Francisco, CA | biking | 7 | 100% | PASS (select_pois_for_day) | 2 | 48.0s | PASS |
| 3 | San Francisco, CA | kids | 7 | 100% | PASS (select_pois_for_day) | 2 | 54.9s | PASS |
| 4 | San Francisco, CA | swimming | 8 | 100% | PASS (select_pois_for_day) | 2 | 42.3s | PASS |
| 5 | San Francisco, CA | kayaking | 9 | 100% | PASS (select_pois_for_day) | 4 | 86.8s | PASS |
| 6 | San Francisco, CA | picnic | 6 | 100% | PASS (select_pois_for_day) | 2 | 44.1s | PASS |
| 7 | San Francisco, CA | hiking, biking | 8 | 100% | PASS (select_pois_for_day) | 2 | 43.9s | PASS |
| 8 | San Francisco, CA | swimming, kids | 5 | 100% | PASS (select_pois_for_day) | 2 | 46.1s | PASS |
| 9 | New York City, NY | hiking | 8 | 0% | PASS (select_pois_for_day) | 3 | 76.4s | FAIL |
| 10 | New York City, NY | biking | 6 | 100% | PASS (select_pois_for_day) | 2 | 42.4s | PASS |
| 11 | New York City, NY | kids | 7 | 100% | PASS (select_pois_for_day) | 2 | 45.3s | PASS |
| 12 | New York City, NY | kayaking | 7 | 100% | PASS (select_pois_for_day) | 2 | 41.4s | PASS |
| 13 | New York City, NY | picnic | 4 | 100% | PASS (select_pois_for_day) | 2 | 40.7s | PASS |
| 14 | New York City, NY | hiking, biking | 8 | 50% | PASS (select_pois_for_day) | 2 | 42.7s | PASS |
| 15 | New York City, NY | swimming, kids | 6 | 100% | PASS (select_pois_for_day) | 2 | 43.3s | PASS |

**Run 3 — Tavily classifier + Tavily enrichment**  
Pass rate: 14/15  
Tool routing accuracy: 15/15  
Avg activity recall: 90%  
Avg plan time: 49.6s  
Enrichment — %rated: 0% | %with reviews: 100% | %with photos: 0% | avg rating: —  
Match quality — %with evidence: 93% | avg match score: 3.73/5  


## Run 4 — OSM + TripAdvisor

| # | City | Activities | Stops | Recall | Routing | Tools | Time | Pass/Fail |
|---|------|------------|-------|--------|---------|-------|------|-----------|
| 1 | San Francisco, CA | hiking | 8 | 100% | PASS (select_pois_for_day) | 2 | 33.6s | PASS |
| 2 | San Francisco, CA | biking | 8 | 0% | PASS (select_pois_for_day) | 4 | 44.3s | FAIL |
| 3 | San Francisco, CA | kids | 5 | 100% | PASS (select_pois_for_day) | 2 | 32.6s | PASS |
| 4 | San Francisco, CA | swimming | 6 | 100% | PASS (select_pois_for_day) | 2 | 41.4s | PASS |
| 5 | San Francisco, CA | kayaking | 8 | 0% | PASS (select_pois_for_day) | 12 | 43.4s | FAIL |
| 6 | San Francisco, CA | picnic | 5 | 100% | PASS (select_pois_for_day) | 12 | 59.8s | PASS |
| 7 | San Francisco, CA | hiking, biking | 8 | 50% | PASS (select_pois_for_day) | 2 | 34.9s | PASS |
| 8 | San Francisco, CA | swimming, kids | 6 | 100% | PASS (select_pois_for_day) | 2 | 28.7s | PASS |
| 9 | New York City, NY | hiking | 8 | 100% | PASS (select_pois_for_day) | 1 | 13.7s | PASS |
| 10 | New York City, NY | biking | 7 | 100% | PASS (select_pois_for_day) | 3 | 44.1s | PASS |
| 11 | New York City, NY | kids | 7 | 100% | PASS (select_pois_for_day) | 3 | 71.8s | PASS |
| 12 | New York City, NY | kayaking | 7 | 100% | PASS (select_pois_for_day) | 2 | 30.6s | PASS |
| 13 | New York City, NY | picnic | 4 | 100% | PASS (select_pois_for_day) | 7 | 56.7s | PASS |
| 14 | New York City, NY | hiking, biking | 6 | 100% | PASS (select_pois_for_day) | 5 | 65.6s | PASS |
| 15 | New York City, NY | swimming, kids | 8 | 100% | PASS (select_pois_for_day) | 2 | 27.7s | PASS |

**Run 4 — OSM + TripAdvisor**  
Pass rate: 13/15  
Tool routing accuracy: 15/15  
Avg activity recall: 83%  
Avg plan time: 41.9s  
Enrichment — %rated: 35% | %with reviews: 23% | %with photos: 35% | avg rating: 4.40  
Match quality — %with evidence: 67% | avg match score: 3.74/5  


## Run 5 — Tavily + TripAdvisor (best-of-all candidate)

| # | City | Activities | Stops | Recall | Routing | Tools | Time | Pass/Fail |
|---|------|------------|-------|--------|---------|-------|------|-----------|
| 1 | San Francisco, CA | hiking | 8 | 100% | PASS (select_pois_for_day) | 4 | 50.3s | PASS |
| 2 | San Francisco, CA | biking | 7 | 100% | PASS (select_pois_for_day) | 2 | 40.1s | PASS |
| 3 | San Francisco, CA | kids | 7 | 100% | PASS (select_pois_for_day) | 2 | 49.6s | PASS |
| 4 | San Francisco, CA | swimming | 8 | 100% | PASS (select_pois_for_day) | 2 | 35.5s | PASS |
| 5 | San Francisco, CA | kayaking | 8 | 100% | PASS (select_pois_for_day) | 2 | 30.8s | PASS |
| 6 | San Francisco, CA | picnic | 6 | 100% | PASS (select_pois_for_day) | 3 | 37.4s | PASS |
| 7 | San Francisco, CA | hiking, biking | 9 | 100% | PASS (select_pois_for_day) | 2 | 39.0s | PASS |
| 8 | San Francisco, CA | swimming, kids | 6 | 100% | PASS (select_pois_for_day) | 2 | 37.6s | PASS |
| 9 | New York City, NY | hiking | 5 | 100% | PASS (select_pois_for_day) | 9 | 57.0s | PASS |
| 10 | New York City, NY | biking | 5 | 100% | PASS (select_pois_for_day) | 4 | 55.0s | PASS |
| 11 | New York City, NY | kids | 5 | 100% | PASS (select_pois_for_day) | 11 | 83.8s | PASS |
| 12 | New York City, NY | kayaking | 7 | 100% | PASS (select_pois_for_day) | 3 | 33.8s | PASS |
| 13 | New York City, NY | picnic | 5 | 100% | PASS (select_pois_for_day) | 2 | 29.3s | PASS |
| 14 | New York City, NY | hiking, biking | 8 | 50% | PASS (select_pois_for_day) | 3 | 44.4s | PASS |
| 15 | New York City, NY | swimming, kids | 7 | 100% | PASS (select_pois_for_day) | 2 | 32.9s | PASS |

**Run 5 — Tavily + TripAdvisor (best-of-all candidate)**  
Pass rate: 15/15  
Tool routing accuracy: 15/15  
Avg activity recall: 97%  
Avg plan time: 43.8s  
Enrichment — %rated: 38% | %with reviews: 25% | %with photos: 38% | avg rating: 4.49  
Match quality — %with evidence: 80% | avg match score: 3.62/5  


## Comparison Across Runs

| Metric | OSM+Synth | Tavily+Synth | Tavily+Enrich | OSM+TA | Tavily+TA |
|--------|-----|-----|-----|-----|-----|
| Pass rate | 13/15 | 15/15 | 14/15 | 13/15 | 15/15 |
| Routing accuracy | 15/15 | 15/15 | 15/15 | 15/15 | 15/15 |
| Avg recall | 83% | 100% | 90% | 83% | 97% |
| Avg time (s) | 66.0 | 70.3 | 49.6 | 41.9 | 43.8 |
| % stops rated | 87% | 86% | 0% | 35% | 38% |
| % stops with reviews | 87% | 86% | 100% | 23% | 25% |
| % stops with photos | 0% | 0% | 0% | 35% | 38% |
| Avg rating | 4.27 | 4.33 | — | 4.40 | 4.49 |
| % matched with evidence | 67% | 80% | 93% | 67% | 80% |
| Avg match quality (1–5) | 3.72 | 3.64 | 3.73 | 3.74 | 3.62 |

## Analysis

### Classifier lift (Run 2 vs Run 1 — Tavily activity vs OSM tags)
- OSM recall: 83%  |  Tavily recall: 100%  |  delta: +17%
- OSM wins when POIs have clear subtype tags (peak=hiking, playground=kids, beach=swimming) — zero cost, zero latency.
- Tavily wins when POIs lack explicit tags but are known for an activity via web content (e.g. a 'nature reserve' known for kayaking).

### Enrichment lift (Run 4 vs Run 1 — TripAdvisor ratings vs LLM-synthetic)
- % stops rated:  OSM+Synth 87%  |  OSM+TA 35%  |  delta: -51%
- % stops with photos:  OSM+Synth 0%  |  OSM+TA 35%  |  delta: +35%
- LLM-synthetic ratings are fabricated — they look complete but carry no signal about real quality.
- TripAdvisor ratings reflect actual visitor reviews and come with photos, making stop cards richer.

### Best-of-all candidate (Run 5 — Tavily classifier + TripAdvisor ratings)
- Activity recall: 97%  |  % stops rated: 38%  |  avg match quality: 3.62/5
- Recommended production config if TAVILY_API_KEY and TRIPADVISOR_API_KEY are available.
- Fall back to Run 1 (OSM+Synth) when neither key is present — still passes all routing tests.
