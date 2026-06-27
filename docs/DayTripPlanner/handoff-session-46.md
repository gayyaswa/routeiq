# Handoff — Session 46

**Date:** 2026-06-25
**Branch:** feature/activity-eval
**Status:** Submission-ready. All code committed. GDoc created. LangSmith wired. One step remaining: record Loom.

---

## What was done this session

### 1. README updated ✅

Added full Week 4 section:
- Week 4 eval table (5-config × 15-query results)
- `routeiq/activities/` package in module layout + project structure
- `select_pois_for_day` and `get_travel_time` as 6th and 7th tools
- `ACTIVITY_CLASSIFIER` env var
- Test count updated 213 → 315 (24 files)
- `docs/week4-submission.md` added to Documentation table

### 2. Committed Week 4 eval (commit 88a44ff) ✅

34 files, 3284 insertions. All new eval infrastructure, architecture docs, submission docs, 5 PNG diagrams, eval results.

### 3. Google Doc content revised (docs/week4-google-doc.md) ✅

Four structural improvements made this session:

**Section 3 — Baseline Run and Failure Analysis:**
- Table now labels each row M1/M2/M3/M4 with pass bar column — connects directly to Section 1 metric definitions
- M3 (LLM-as-judge) explicitly shown as "not measured" at baseline with explanation
- Failure analysis reorganized under M1/M2/M4 subheadings — each bug ends with "→ Fixes M2 for X configs"
- "Dominant failure" section repositioned under M1 as "fixed before this run"

**Section 5 — Post-Improvement Results:**
- Added "Metric Improvement Summary" table at the top: M1–M4 + Overall pass rate, baseline vs post-improvement, key driver column
- Note explaining OSM+Synth M2 apparent drop (100% → 83%) is scope expansion not regression

**Section 5 — 5-Config Comparison Summary:**
- Replaced vague "Key findings" bullets with "Which config to use" recommendation matrix table (4 rows: best recall / best all-around / no API keys / fastest)
- Added "Gaps where no current config does well" table: photos, real ratings for trails, multi-activity recall, picnic OSM — each with root cause and proposed fix

**Section 7 — What's Next:**
- Rewritten to flow from the 4 gaps in Section 5
- Four improvements A–D ordered by eval impact with expected deltas
- Production monitoring converted to a table with 3 signals and plain-English explanations
- Confusing "activity_recall < 50% on 50-run rolling average" line removed and replaced with single-run threshold
- Edge-case Q16–Q30 note clarified: intentionally deferred until Improvements A+B are implemented

### 4. M3 rubric added to Section 1 ✅

`Activity match quality (LLM-as-judge)` now shows the full 5-point rubric verbatim from `eval/evaluators.py:26-31`:
- 1 = Unrelated / misleading
- 2 = Tenuous connection
- 3 = Reasonable but not ideal
- 4 = Good match
- 5 = Excellent, clearly designed for this activity

Plus pass bar (≥3.5) and interpretive anchors.

### 5. Caches pre-populated and committed (commit 69339fb) ✅

299 files. Zero cold-start for anyone cloning the repo:
- `cache/activities/` — 12 Tavily activity classification caches (SF + NYC, all 6 activities)
- `cache/ratings/llm_synthetic_new_york_city_ny.json` — 40-entry NYC synthetic ratings
- `cache/ratings/llm_synthetic_austin_tx.json` — Austin
- `cache/ratings/tavily_enrich_*.json` — SF + NYC Tavily enrichment caches
- `cache/ratings/tripadvisor_photos_*.json` — 210 real TripAdvisor photo caches
- `cache/chroma/` — updated vector store with NYC POIs
- 24 handoff session files deleted (were already gitignored, cleaned from disk)
- 5 root-level course assignment files deleted (Social Media Post *.md/xlsx/json, Week4 Handout copies)

### 6. Loom script saved (docs/week4-loom-script.md) ✅

6-section script (~5 min): new features → metrics → baseline → improvements → post-run → future work. Key numbers at the bottom for quick reference during recording.

### 7. LangSmith verified ✅

`.env` confirmed: `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_PROJECT=routeiq-week4`. Traces visible in LangSmith Tracing tab. URL added to Google Doc. Note: per-run public sharing requires paid plan; project-level URL or screenshot used instead.

### 8. HTML export generated (docs/week4-google-doc.html) ✅

`pandoc docs/week4-google-doc.md → docs/week4-google-doc.html` with clean CSS. Open in browser, Cmd+A, Cmd+C, paste into Word — preserves tables/headers/bold.

### 9. Refinement timing display fixed (commit 84af5bd) ✅

**Bug:** After a refinement, the "Planned in Xs" metric and "Step breakdown" line were not displayed.

**Root cause:** `dt_plan_start = time.perf_counter()` was set before the initial plan thread (line 698) but NOT before the refinement thread (line 862). The planning poll popped `None` → `dt_plan_elapsed = None` → entire timing block skipped.

**Fix:** Added `st.session_state["dt_plan_start"] = time.perf_counter()` one line before `t.start()` in the refinement path. One-line change. 315/315 tests still passing.

### 10. Rate_pois slow on refinement — root cause identified ✅

**Symptom:** Refine "beaches keep family friendly" → Rating stops: 189s even on a "warm" run.

**Root cause:** The LLM synthetic cache is keyed by POI name. The initial plan (e.g. hiking) caches hiking/scenic POIs. Refinement with "beaches" brings in a new coastal POI pool never seen before → all cache misses → 2 LLM batches × ~75s = ~150s + Wikipedia fetches for new POIs.

**This is not a regression** — first run of any new POI category is always cold. Subsequent refinements to beaches will be fast (cache warm).

**Mitigation for Loom demo:** Run one beach query in the app before recording to pre-warm the cache.

**Proper code fix (future):** `rate_pois` should accept already-rated POIs from the current draft and skip re-rating them on refinement, paying LLM cost only for genuinely new POIs.

---

## Commits this session

| Hash | Message |
|------|---------|
| `88a44ff` | feat: Week 4 eval complete — 15-query smoke test, 5 configs, 9 improvements |
| `69339fb` | chore: pre-populate all caches + clean up docs for submission |
| `84af5bd` | fix: show plan timing after refinement |

---

## Current state

- **Branch:** `feature/activity-eval`
- **Tests:** 315/315 passing
- **Git:** clean (no uncommitted changes)
- **Google Doc:** created ✅
- **LangSmith:** wired and verified ✅
- **Submission due:** 2026-06-27

---

## What needs to be done next session (in order)

### Step 1 — Pre-warm beach cache for Loom (5 min)
Run one SF beach query in the app before recording:
- City: San Francisco, CA
- Activities: swimming (or leave blank and type "beaches" in the text box)
- This populates beach/coastal POIs in `cache/ratings/llm_synthetic_san_francisco_ca.json`
- After this run, any beach refinement will be fast (<5s for Rating stops)

### Step 2 — Record Loom (~5 min)
Script: `docs/week4-loom-script.md`

Sections:
1. (0:00–0:50) New features — `select_pois_for_day`, two-track merge, OSM/Tavily classifiers
2. (0:50–1:40) Metrics M1–M4 — routing, recall, LLM-judge rubric (1=unrelated → 5=excellent), plan time
3. (1:40–2:40) Baseline run — M1 already 100% (fix applied), M2 biking failed 3/5 configs, M4 cold Tavily blown
4. (2:40–3:30) 9 improvements — control flow, 5 data pipeline bugs, 2 cache fixes, ReAct loop (12 → 2–3 iterations)
5. (3:30–4:20) Post-run — 15/15 routing all configs, Tavily +17% recall, recommend Tavily+TA
6. (4:20–5:00) Future work — photos gap, multi-activity ceiling, picnic OSM fix

Key numbers to cite: routing 15/15, recall 83→100% (+17%), iterations 12→2–3, plan time 226s→30s, 315 tests, 9 improvements.

### Step 3 — Submit (4 URLs)
- [x] Google Doc URL
- [x] LangSmith project URL
- [ ] GitHub: `feature/activity-eval` branch link
- [ ] Loom recording URL

### Step 4 — Merge to main (optional, after submission)
```bash
git checkout main
git merge feature/activity-eval
git push
```

---

## Known gaps (acknowledge in Loom, not blockers)

| Gap | Impact | Proposed fix |
|-----|--------|-------------|
| Picnic 0% recall in OSM configs (Q6, Q13) | 2/15 queries | Add `leisure=picnic_site` to OSM fetcher |
| Multi-activity recall ceiling 50% (Q14) | All ≥2-activity queries | Raise slot floor: min(2, budget÷2) per activity |
| Photos 0% in 3/5 configs | Trail/park stops have no image | Wikimedia Commons geo-image fallback |
| Refinement cold cache on new POI category | First beach/picnic refine ~189s | Pre-rate new category POIs on refine, not full pool |
| Edge-case Q16–Q30 not yet run | Intentionally deferred | Run after Improvements A+B implemented |
