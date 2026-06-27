# Week 4 Submission Checklist

**Due:** 2026-06-27 | **Track:** Evaluate Your Own Agent (LangSmith)

---

## Done ✅

- [x] Tool routing eval — 8/8 (100%) — `eval/results_tool_routing.md`
- [x] Smoke test — 15 queries × 5 configs — `eval/results_week4.md`
  - Routing 15/15 (100%) in every config
  - Recall 83–100% across configs
  - ReAct iterations 12 → 2–3 (Improvement 9 verified)
- [x] 9 improvements implemented and documented
- [x] README updated — Week 4 eval section, 6 tools, 315 tests, activities/ package
- [x] Architecture docs updated — `docs/agent-architecture.md`, `docs/Architecture-and-Design-Decisions.md`
- [x] 315/315 tests passing
- [x] Everything committed — branch `feature/activity-eval` (commit 88a44ff)
- [x] Google Doc created ✓
- [x] Loom script saved — `docs/week4-loom-script.md`

---

## Remaining (in order)

### 1. Add LangSmith URL to Google Doc ✅
- [x] `.env` confirmed — `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_PROJECT=routeiq-week4`
- [x] Traces visible in LangSmith Tracing tab
- [x] LangSmith URL added to Google Doc

### 2. Record Loom (~5 min)
- [ ] Open `docs/week4-loom-script.md` for the script
- [ ] Screen share the Google Doc, scroll through each section as you talk
- [ ] 6 sections: new features → metrics → baseline → improvements → post-run results → future work
- [ ] Key numbers to mention: routing 15/15, recall +17% Tavily lift, 12→2–3 iterations, 226s→30s plan time

### 3. Final repo check
- [ ] Verify `requirements.txt` is current: `pip freeze | grep -E "langchain|langgraph|osmnx|chromadb|tavily"`
- [ ] Merge `feature/activity-eval` to `main` — OR confirm submission accepts branch link

### 4. Submit
- [ ] Google Doc URL ✓ (created)
- [ ] LangSmith project URL (after Step 1)
- [ ] GitHub repo link — `feature/activity-eval` branch
- [ ] Loom recording URL (after Step 2)

---

## Known gaps to mention in Loom (not blockers)

| Gap | Impact | One-line fix |
|-----|--------|-------------|
| Picnic 0% recall in OSM configs (Q6, Q13) | 2/15 queries fail without Tavily | Add `leisure=picnic_site` to OSM fetcher |
| Multi-activity recall ceiling at 50% (Q14) | All configs, structural | Raise slot floor when ≥2 activities |
| Photos 0% in 3/5 configs | Trail/park stops have no image | Wikimedia Commons geo-image fallback |
