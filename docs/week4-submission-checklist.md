# Week 4 Submission Checklist

Submission due: Friday (2026-06-27). Track: **Evaluate Your Own Agent (Track 3 / LangSmith)**.

Deliverables per handout: evaluation report + golden dataset + LangSmith project link + Loom walkthrough.

---

## Must-do before submission

### Evals (blocking)

- [x] Tool routing eval — 8/8 routing pass rate confirmed (`eval/results_tool_routing.md`)
- [x] Improvement 9 verified — iter=2 STOP, no wasted `estimate_visit_duration` / `enrich_poi_details` calls
- [ ] `--limit 15` smoke test passing — SF Q1–8 + NYC Q9–15, Run 1 (OSM+Synth)
- [ ] Full eval run — `python3 eval/run_week4_eval.py` → `eval/results_week4.md`
  - Expected: ~150 agent calls, ~5–8 hours
  - Requires: `NEBIUS_API_KEY` (or `ANTHROPIC_API_KEY`), optionally `TAVILY_API_KEY`, `TRIPADVISOR_API_KEY`
  - If no Tavily/TA keys: Runs 2, 3, 5 degrade gracefully; report what's available

### Submission doc (docs/week4-submission.md)

- [x] Section 1 — Eval one-liner ✓
- [x] Section 2 — What Week 4 adds ✓
- [x] Section 3 — The four metrics ✓
- [x] Section 4 — Golden datasets ✓
- [x] Section 5 — Eval configurations ✓
- [x] Section 6 — Baseline run + failure analysis ✓ (3-case sanity + 5 root causes documented)
- [x] Section 6 — Tool routing eval table filled (was PLACEHOLDER, now 8/8 results) ✓
- [ ] Section 6 — Full 30-query comparison table (fill after full eval run)
- [x] Section 7 — 9 improvements documented ✓
- [x] Section 8 — Eval instrumentation ✓
- [x] Section 9 — LangSmith observability + performance analysis + timing diagrams ✓
- [x] Section 10 — What's next ✓
- [ ] Update recommended config in Section 10 after full eval (may change from OSM+Synth to Tavily+TA)

### Architecture docs

- [x] `docs/agent-architecture.md` — Week 4 layer added (activities, new tool, ReAct fix, eval) ✓
- [x] `docs/Architecture-and-Design-Decisions.md` — Week 4 decisions added (7 new entries) ✓
- [ ] `docs/eval_week4/data-flows.md` — verify data flow diagrams are current (subtype fix, two-track merge)

### README

- [ ] Update README with Week 4 eval section — at minimum add:
  - New `routeiq/activities/` package one-liner
  - Updated tool list (now 6 tools)
  - How to run the eval: `python3 eval/run_week4_eval.py`
  - Pass bars: routing 8/8, recall ≥70%, p95 <90s

### Tests

- [x] 315/315 passing ✓

---

## Loom walkthrough (~5 min)

Required content (from handout):
- [ ] What changed from Week 3 (activity layer, 6th tool, two-track merge)
- [ ] Show a live query: SF hiking → `select_pois_for_day` called → activity-matched stops appear
- [ ] Show `logs/timing.log` or a LangSmith trace: iter=2 STOP (vs. 12 before)
- [ ] Walk through the 5-config comparison table from `eval/results_week4.md`
- [ ] Name the dominant failure mode (picnic 0% recall — no `picnic_site` OSM subtypes in SF cache)
- [ ] What you'd do with another week (seed `picnic_site` / `garden` POIs, Tavily for ambiguous tags)

Suggested structure:
1. (0:00–0:45) What Week 4 adds — one slide or the week4-submission.md Section 2
2. (0:45–2:00) Live demo — SF hiking query, show stop cards, explain activity vs scenic track
3. (2:00–3:30) Timing / LangSmith trace — show iter=2 STOP, mention the 12→2 fix
4. (3:30–4:30) Eval results — comparison table, routing accuracy, recall by config
5. (4:30–5:00) What still fails and what's next

---

## LangSmith

- [ ] Confirm `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_PROJECT=routeiq-week4` are set in `.env`
- [ ] Trigger one manual run and verify trace appears in LangSmith UI (every LLM call + every tool call visible)
- [ ] Grab the LangSmith project URL for the submission doc

---

## GitHub repo

- [ ] Commit everything on `feature/activity-eval`:
  - `eval/results_week4.md` (from full eval)
  - `eval/results_tool_routing.md` (already generated)
  - `docs/week4-submission.md` (with filled Section 6)
  - `docs/agent-architecture.md` (Week 4 additions)
  - `docs/Architecture-and-Design-Decisions.md` (Week 4 decisions)
  - `docs/images/eval_*.png` (5 diagrams)
  - All modified `routeiq/` source files
- [ ] Merge to `main` (or confirm branch is linked in submission)
- [ ] Verify `requirements.txt` is up to date (`python3 -m pip freeze | grep -E "langchain|langgraph|osmnx|chromadb|tavily"`)

---

## Known gaps (document, don't fix)

These are known failures to acknowledge in the Loom walkthrough — not blockers:

| Gap | Impact | Root cause |
|-----|--------|-----------|
| Q6 / Q13 picnic 0% recall | OSM SF/NYC cache has no `picnic_site` or `garden` subtypes | `leisure=picnic_site` not in tourism/historic fetcher |
| NYC LLM-synthetic cold cache | First NYC query ~10s slower; cache builds up over eval run | `new_york_city_ny.json` didn't exist before today's run |
| Wikipedia write race (11→22 entries) | Occasional shorter cache snapshot with 6 threads | `_write_cache` not protected by `_cache_lock`; low priority |
| Berkeley/San Jose scenic queries 150–260s | Token overflow on Berkeley (8192 completion tokens) | Large POI pool → long context; add `max_tokens` guard or pre-filter |

---

## Order of operations today/tomorrow

1. **[now running]** `--limit 15` smoke test — verify SF + NYC happy-path all pass
2. Check NYC rating times in output — if >60s seed NYC cache (likely auto-seeded by Q9)
3. Run full eval: `python3 eval/run_week4_eval.py`
4. Fill Section 6 comparison table in `docs/week4-submission.md`
5. Update Section 10 recommended config if eval changes the picture
6. Update README
7. Verify LangSmith tracing live
8. Record Loom
9. Commit + submit
