# Eval Plan — Session 38

*Approved 2026-06-23. Implements expanded provider comparison + LLM-as-judge match quality.*

---

## Handout Field Coverage Map

| Handout Field | Current Status | This Plan's Contribution |
|---|---|---|
| **Eval one-liner** | ✅ written | Update to include match quality + rating/photo |
| **Agent under test** | ✅ | No change |
| **User outcome** | ✅ | No change |
| **Metrics (3–5)** | ✅ 4 metrics | +2 activity quality: `pct_with_evidence` (code), `avg_match_quality` (LLM-judge). +4 enrichment: `avg_rating`, `%rated`, `%with_reviews`, `%with_photos` |
| **Judge method** | ✅ code-based only | **+ LLM-as-judge** for match quality (satisfies handout "combine ≥2 types") |
| **Golden dataset** | ✅ 38 cases | No change |
| **Pass bar** | ✅ routing/recall/time | No pass bar for enrichment/match quality (comparison signal only) |
| **Instrumentation** | ✅ LangSmith `routeiq-week4` | No change |
| **Baseline run** | ⚠️ PLACEHOLDER | Run 1 numbers fill this after eval completes |
| **Failure analysis** | ✅ tool routing bug | No change |
| **Improvements (3–4)** | ✅ 2 behavioral fixes | Provider comparison IS Improvement 3: "switched from llm_synthetic to TripAdvisor; measured delta on rating completeness and photo presence" |
| **Post-improvement run** | ⚠️ PLACEHOLDER | Tool routing eval (r1–r8) fills this |
| **What's next** | ✅ written | Update: Tavily+TripAdvisor as recommended production config |

---

## Provider Comparison Matrix (5 runs)

| Run | `ACTIVITY_PROVIDER` | `RATING_PROVIDER` | What it isolates |
|-----|--------------------|--------------------|-----------------|
| 1 — Baseline | `osm` | `llm_synthetic` | Tag-based activity + synthetic ratings |
| 2 — Classifier lift | `tavily` | `llm_synthetic` | Tavily activity inference vs OSM |
| 3 — Full Tavily | `tavily` | `tavily_enrichment` | Tavily activity + Tavily enriched ratings |
| 4 — OSM + TA | `osm` | `tripadvisor` | OSM activity + real TripAdvisor ratings/photos |
| 5 — Tavily + TA | `tavily` | `tripadvisor` | Best-of-all combination candidate |

---

## New Metrics

### Activity Match Quality (LLM-as-judge)
- **`avg_match_quality`** — LLM scores each activity-matched stop 1–5 on how well it suits the requested activity
- **`pct_with_evidence`** — Code-based: fraction of matched stops with non-empty `activity_evidence` field

**Judge prompt:**
```
Activity requested: {activity}
POI: {poi_name}
Description: {why_visit or activity_evidence}

Rate 1-5 how well this POI suits the requested activity:
1 = Unrelated / misleading
2 = Tenuous connection
3 = Reasonable but not ideal
4 = Good match
5 = Excellent, clearly designed for this activity

Reply with only a single integer 1-5.
```

### Enrichment Quality (code-based, from `rate_pois` ToolMessage)
- **`pct_rated`** — fraction of stops with a non-None `rating`
- **`pct_with_reviews`** — fraction with non-empty `all_snippets`
- **`pct_with_photos`** — fraction with non-empty `photo_urls`
- **`avg_rating`** — mean rating of rated stops

---

## Files to Change

| File | Change |
|---|---|
| `eval/evaluators.py` | Add `score_enrichment_quality()`, `score_activity_match_quality()`, wire into `ActivityEvaluator.score()`; accept `llm` param in `__init__` |
| `eval/run_week4_eval.py` | Add Runs 4+5; create shared `llm`; add 6 metric rows to comparison table; update `_summary()` |
| `docs/week4-submission.md` | Eval one-liner, Sections 3/5/7/9 |

---

## Verification Steps

```bash
python3 -m pytest tests/ -v                            # 315 passed
python3 -c "from eval.evaluators import score_enrichment_quality, score_activity_match_quality; print('ok')"
python3 -c "from eval.run_week4_eval import RUNS; print(len(RUNS), 'runs')"  # → 5 runs
python3 eval/run_tool_routing_eval.py                  # 8/8 routing pass
python3 eval/run_week4_eval.py > eval/run_week4_eval_log.txt 2>&1 &  # background
```
