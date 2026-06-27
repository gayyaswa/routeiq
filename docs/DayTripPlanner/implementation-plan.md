# Activity-Based Day Trip Planning — Implementation Plan

Derived from: `activity-planning-spec.md`
Builds on: existing `POIRatingProvider` Strategy pattern, `RouteKnowledgeGraph`, LangGraph agent

---

## Step 0 — Data model changes (no logic yet)

**File:** `routeiq/ratings/base.py`

Add one field to `RatedPOI`:
```python
matched_activities: list[str] | None = None
# populated by ActivityClassifier; carried through to narrate node
```

Add new dataclass `ClassifiedPOI` to a new file `routeiq/activities/base.py`:
```python
@dataclass
class ClassifiedPOI:
    poi: POI
    matched_activities: list[str]     # e.g. ["hiking", "biking"]
    activity_evidence: str | None     # human-readable source: "Tavily: 'coastal trail'"
```

No behavior changes yet — just shapes.

---

## Step 1 — `ActivityClassifier` ABC

**File:** `routeiq/activities/base.py`

```python
class ActivityClassifier(ABC):
    @abstractmethod
    def classify_batch(
        self,
        city: str,
        pois: list[POI],
        activities: list[str],
    ) -> list[ClassifiedPOI]:
        ...
```

One method. Returns every input POI as a `ClassifiedPOI` — unmatched ones get
`matched_activities=[]`. Caller decides what to do with empties.

---

## Step 2 — `OSMActivityClassifier` (free baseline, no API)

**File:** `routeiq/activities/osm_classifier.py`

Static map from OSM tags already on `POI` objects to activity strings:

```python
_OSM_ACTIVITY_MAP = {
    "leisure=cycling_path": "biking",
    "leisure=track":        "biking",
    "natural=peak":         "hiking",
    "leisure=nature_reserve": "hiking",
    "amenity=playground":   "kids",
    "tourism=theme_park":   "kids",
    "leisure=swimming_pool": "swimming",
    "natural=beach":        "swimming",
    "sport=kayaking":       "kayaking",
    # extend as needed
}
```

`classify_batch`: for each POI, check `poi.category` / OSM tags against map.
No network calls. 21-day cache not needed — pure in-memory lookup.

This is the **eval baseline** — what we score against before adding Tavily/Perplexity.

---

## Step 3 — `TavilyActivityClassifier`

**File:** `routeiq/activities/tavily_classifier.py`

Bulk fetch pattern — 1 Tavily search per `(city, activity)`, not per POI:

```
classify_batch(city, pois, activities):
  for activity in activities:
    cache_key = f"tavily_{city}_{activity}"
    if cache hit (21 days): load results
    else:
      results = tavily.search(f"{activity} in {city} places")
      cache results
    
    # LLM structured call (short, cheap):
    # "Given these web results, which of these POI names are mentioned
    #  as good for {activity}? Return JSON list of matched names."
    matched_names = llm_extract(results, [p.name for p in pois])
    
    for poi in pois:
      if poi.name in matched_names:
        classified[poi.id].matched_activities.append(activity)
        classified[poi.id].activity_evidence = f"Tavily: {top_snippet}"
```

API calls per planning session: `len(activities)` searches/city, cached for 21 days.
Typical: 2–3 activities → 2–3 Tavily calls total, then 0 for 21 days.

---

## Step 4 — `PerplexityActivityClassifier`

**File:** `routeiq/activities/perplexity_classifier.py`

One call per city covers all activities at once:

```
classify_batch(city, pois, activities):
  cache_key = f"perplexity_{city}_{sorted(activities)}"
  if cache hit (21 days): load
  else:
    q = f"In {city}, which specific venues or parks are known for: 
         {', '.join(activities)}? For each venue, list which activities apply."
    answer = perplexity.query(q)   # returns answer + citations
    cache answer
  
  # LLM structured extraction:
  # parse (venue_name, activity) pairs from Perplexity answer
  # match venue names to pois by name similarity (ChromaDB, same pattern as TripAdvisor)
```

API calls: 1 per city per session, cached 21 days.

---

## Step 4b — `TavilyEnrichmentProvider` (Tavily as rating provider)

**File:** `routeiq/ratings/tavily_enrichment.py`

Tavily serves double duty — classifier AND enrichment provider. Different queries,
different cache keys, different outputs. Both implement separate ABCs.

```
enrich_batch(city, pois):
  # Bulk search — one query covers multiple POIs
  results = tavily.search(f"visitor highlights reviews attractions {city}")
  cache: f"tavily_enrich_{city}.json"  (21-day TTL, different from classifier cache)

  # Per-POI fallback only if bulk result has no match (rare)
  for poi in pois where no bulk match:
    results = tavily.search(f"{poi.name} {city} visitor experience")
    cache: f"tavily_enrich_{poi_id}.json"

  LLM structured extraction per matched POI (short call ~150 tokens):
    → rating_hint   : "consistently well-reviewed" / "mixed reviews"
    → highlights    : list[str], max 3 bullets
    → visitor_quote : single best quote from results
    → photo_url     : first image URL if present
```

**`LLMSyntheticRatingProvider` stays** — it is not replaced by Tavily enrichment:
- Used as the **eval baseline** (measures floor before real data)
- Fallback when Tavily returns no useful results for an obscure POI
- Works fully offline — no API key needed
- Running both in eval directly measures the quality lift Tavily provides

Register in `factory.py`:
```python
if provider == "tavily_enrichment":
    return TavilyEnrichmentProvider(api_key=os.getenv("TAVILY_API_KEY"))
```

---

## Step 4c — `ActivityRanker` (pick best POI per activity slot)

**File:** `routeiq/activities/ranker.py`

After classification tags POIs, multiple candidates may qualify for the same activity slot.
The ranker picks the best one per slot based on user context + available ratings.

```python
class ActivityRanker(ABC):
    """Ranks classified POI candidates for a single activity slot."""
    @abstractmethod
    def rank(
        self,
        candidates: list[ClassifiedPOI],   # all POIs tagged with this activity
        activity: str,                      # "hiking"
        user_context: str,                  # "scenic coastal hiking" or just "hiking"
        ratings: dict[str, float],          # poi_id → rating (empty if not yet enriched)
    ) -> list[ClassifiedPOI]:              # ranked best-first
        ...
```

Three implementations:

**`RatingRanker`** — sort by available rating descending. Simple, fast, no LLM call.
Use when: ratings are available and user gave no specific adjectives.

**`SemanticRanker`** — embed `user_context` and each POI's `activity_evidence`;
rank by cosine similarity. Use when user gave descriptive adjectives ("scenic",
"challenging", "family-friendly", "coastal").

**`LLMRanker`** — single LLM call: "Given these candidates and the user wants
'{user_context}', rank them best to worst." Most accurate but costs one LLM call.
Use when: conflicting signals or complex multi-criteria preferences.

Default selection logic in `ActivityClassifierFactory`:
```python
def create_ranker(user_context: str) -> ActivityRanker:
    adjectives = ["scenic", "challenging", "easy", "coastal", "family", "hidden"]
    if any(adj in user_context.lower() for adj in adjectives):
        return SemanticRanker()
    if ratings_available:
        return RatingRanker()
    return LLMRanker()
```

---

## Step 5 — `ActivityClassifierFactory`

**File:** `routeiq/activities/factory.py`

```python
def create_activity_classifier() -> ActivityClassifier:
    provider = os.getenv("ACTIVITY_PROVIDER", "osm")
    if provider == "tavily":
        return TavilyActivityClassifier(api_key=os.getenv("TAVILY_API_KEY"))
    if provider == "perplexity":
        return PerplexityActivityClassifier(api_key=os.getenv("PERPLEXITY_API_KEY"))
    return OSMActivityClassifier()   # free default
```

`__init__.py` re-exports `ActivityClassifier`, `ClassifiedPOI`, `ActivityRanker`,
`create_activity_classifier`.

---

## Step 6 — `POISelector` (two-track merge, now uses ranked candidates)

**File:** `routeiq/routing/poi_selector.py`

```python
class POISelector:
    """Merges activity-matched POIs (Track 1) and scenic fills (Track 2) into a day itinerary."""

    def select(
        self,
        classified_pois: list[ClassifiedPOI],
        requested_activities: list[str],
        total_stops: int = 5,
    ) -> list[ClassifiedPOI]:
        n_activity_slots = min(len(requested_activities), 3) if requested_activities else 0
        n_scenic_slots = total_stops - n_activity_slots

        track1 = [
            p for p in classified_pois
            if set(p.matched_activities) & set(requested_activities)
        ]
        track1 = self._dedupe_by_activity(track1, requested_activities)[:n_activity_slots]

        used_ids = {p.poi.id for p in track1}
        track2 = [
            p for p in classified_pois
            if p.poi.id not in used_ids
        ]
        track2 = sorted(track2, key=lambda p: p.poi.scenic_score, reverse=True)[:n_scenic_slots]

        return self._order_by_geography(track1 + track2)
```

`_dedupe_by_activity`: ensures each requested activity gets at most 1 slot when possible.
`_order_by_geography`: sorts by lat/lon for a logical day flow (existing routing logic).

---

## Step 7 — Parser changes (extract activities from query)

**File:** `routeiq/insights/prompts/query_parser.py`

Add `activities: list[str]` to the structured output schema alongside existing
`origin`, `destination`, `preferences`. Parser prompt gets one new instruction:

> "Extract any specific activities the user wants to do (hiking, biking, swimming, kids
>  activities, etc.) as a list. Return [] if none mentioned."

Bump to `QUERY_PARSER_PROMPT_V3`. Keep V2 as fallback.

---

## Step 8 — New agent tool: `select_pois_for_day`

**File:** `routeiq/agent/tools/select_pois_for_day.py`

Replaces / extends the existing `find_city_pois` flow:

```
Input:  city, requested_activities, user_context, total_stops=5
Steps:
  1. kg.get_pois_for_city(city)                                  — existing KG lookup
  2. classifier.classify_batch(city, pois, activities)            — NEW classify
  3. ranker.rank(candidates, activity, user_context, ratings={}) — NEW rank per activity
  4. selector.select(ranked_classified_pois, activities)          — NEW two-track merge
  5. return selected pois with matched_activities field populated
```

The existing `find_city_pois` tool stays for backward compat (UC-6, no activities).
Agent uses `select_pois_for_day` when `activities` is non-empty in state.

---

## Step 9 — Narrate node update

**File:** `routeiq/agent/day_trip_agent.py` (`_narrate` method)

Narrate prompt gains awareness of the two tracks:

> "For each stop, if matched_activities is non-empty, mention the specific activity and
>  cite the evidence. Do not claim any activity not present in matched_activities.
>  For scenic fills (matched_activities=[]), describe scenic quality and ratings only."

Bump to `NARRATIVE_PROMPT_V3`.

---

## Step 10 — UI badge (Streamlit)

**File:** `app.py`

Stop card already renders `RatedPOI`. Add one conditional:

```python
if rated_poi.matched_activities:
    for act in rated_poi.matched_activities:
        st.badge(act.title(), color="green")   # e.g.  [Hiking]  [Biking]
```

No structural UI changes — just an extra badge line per card.

---

## Step 11 — Graceful fallback (UC-4, UC-8)

**File:** `routeiq/agent/day_trip_agent.py` (conditional edge after `select`)

After `select_pois_for_day`, check coverage:
```
uncovered = requested_activities - {a for p in selected for a in p.matched_activities}
if uncovered:
    state["activity_fallback_note"] = (
        f"We couldn't find {', '.join(uncovered)} options in {city}. "
        f"We've filled those slots with the best scenic alternatives."
    )
```

Narrate node includes `activity_fallback_note` in the response when set.

---

## Step 12 — Tests

| Test file | What it covers |
|---|---|
| `tests/test_osm_classifier.py` | Static tag map; known POI categories return expected activities |
| `tests/test_poi_selector.py` | Two-track merge logic; slot counts; dedup by activity; geo ordering |
| `tests/test_select_pois_tool.py` | Agent tool integration; mock classifier; KG lookup |
| `tests/test_query_parser_v3.py` | Parser extracts activities correctly from UC-1 through UC-5 queries |

Run after each step: `python3 -m pytest tests/ -v`

---

## Step 13 — LangSmith eval wiring

1. Set `LANGCHAIN_PROJECT=routeiq-week4` in `.env`
2. Upload 30-case golden dataset via `langsmith_dataset.py` script
3. Write evaluators:
   - `eval_activity_recall.py` — code-based precision/recall on classifier
   - `eval_activity_coverage.py` — code-based coverage of requested activities
   - `eval_ranking_quality.py` — did the top-ranked candidate match user description?
   - `eval_enrichment_quality.py` — Tavily vs. LLM synthetic highlights comparison
   - `eval_faithfulness.py` — LLM-as-judge on narrative claims vs. evidence
4. Run baseline: `ACTIVITY_PROVIDER=osm`, `RATING_PROVIDER=llm_synthetic`
5. Run Tavily classify: `ACTIVITY_PROVIDER=tavily`, `RATING_PROVIDER=llm_synthetic`
6. Run Tavily full: `ACTIVITY_PROVIDER=tavily`, `RATING_PROVIDER=tavily_enrichment`
7. Run Perplexity: `ACTIVITY_PROVIDER=perplexity`, `RATING_PROVIDER=tavily_enrichment`
8. Compare all runs in LangSmith; report delta table per metric per configuration

---

## Build order summary

```
── Pure logic (no API calls) ─────────────────────────────────────
Step 0    RatedPOI + ClassifiedPOI data model
Step 1    ActivityClassifier ABC
Step 2    OSMActivityClassifier       ← free baseline, zero API
Step 4c   ActivityRanker ABC + RatingRanker + SemanticRanker
Step 5    ActivityClassifierFactory
Step 6    POISelector (two-track merge, uses ranked candidates)

── New API providers ─────────────────────────────────────────────
Step 3    TavilyActivityClassifier    ← classify: 1 search/activity/city
Step 4    PerplexityActivityClassifier ← classify: 1 query/city
Step 4b   TavilyEnrichmentProvider   ← enrich: bulk search + LLM extract
          LLMSyntheticRatingProvider  ← stays, used as eval baseline

── Agent wiring ──────────────────────────────────────────────────
Step 7    Query parser V3             ← extracts activities + user_context
Step 8    select_pois_for_day tool    ← classify → rank → select
Step 9    Narrate node V3             ← two-track voice + grounded claims
Step 10   UI activity badge
Step 11   Graceful fallback

── Verification ──────────────────────────────────────────────────
Step 12   Tests
Step 13   LangSmith eval wiring + golden dataset
```

Steps 0, 1, 2, 4c, 5, 6 are pure logic — build and test these before any API keys.
Steps 3, 4, 4b introduce API calls — each cacheable on first run.
Steps 7–11 wire it all into the live agent — test end-to-end after each.
Step 13 is the Week 4 deliverable.
