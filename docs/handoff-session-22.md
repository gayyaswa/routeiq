# RouteIQ — Session 22 Handoff

**Date:** 2026-06-16
**Branch:** `feature/routeiqagent`
**Tests:** 166 passing (unchanged — planning session only)
**Status:** Phase 1 + Phase 2 COMPLETE. This session was design/planning only.
Phase 3 (agent graph + prompt) + Phase 4 (UI + seed script) remain — full build next session.

---

## What changed this session (design decisions only, no code written)

### Ratings layer — TripAdvisor added as primary provider

| Decision | Detail |
|---|---|
| **TripAdvisor = primary** | User obtained TripAdvisor Content API (Terra) key; higher quality data than Foursquare |
| **Foursquare = secondary** | Stays as swappable option via `RATING_PROVIDER=foursquare` |
| **Single-source traceability** | Every `RatedPOI` always has `review_source` — never mixed across providers |
| **3 reviews per POI** | TripAdvisor returns up to 3 reviews; all 3 passed to LLM as `all_snippets` so it can pick the catchiest for `visitor_quote` |
| **5 photos per POI** | TripAdvisor photos replace Wikipedia thumbnails in stop cards; Wikipedia stays as fallback |
| **`source_name` on ABC** | `POIRatingProvider` gets `@property @abstractmethod source_name: str` — each provider declares its name; UI badge updates automatically on provider swap |

### Day Trip stop card — new fields

```json
{
  "visitor_quote": "Visitors on TripAdvisor call it 'unmissable at golden hour'",
  "review_source": "TripAdvisor",
  "activities": ["Hike the coastal trail", "Watch sunset from Eagle Point"],
  "photo_urls": ["url1", "url2", "url3"],
  "why_visit": "One factual sentence from Wikipedia only.",
  ...
}
```

- `visitor_quote`: LLM picks catchiest of `all_snippets`, prefixes with `review_source`
- `activities`: derived ONLY from Wikipedia description + provider review snippets (grounded, not invented). OSM subtype as last-resort fallback (one generic activity).
- `photo_urls`: TripAdvisor photos (up to 5); `image_url` = Wikipedia thumbnail fallback

### UI — tab order flipped

Day Trip Planner is now **tab 1** (first/default). Route Planner is tab 2.
Reason: Day Trip Planner is the richer, more impressive feature — leads the demo.

### Scope Definition — submission doc strategy

Day 2 submission scored **7/10 on Scope Definition** (all other rubric areas maxed).
Gap: graders couldn't quickly see *what problem, for whom, why this architecture*.

Documents to create/update next session alongside the code:
- `docs/scope-definition.md` — NEW 1-pager: problem statement, target user, explicit in/out-of-scope, why GraphRAG + agent vs. alternatives, how we evaluate
- `docs/agent-architecture.md` — add formal Scope section with interrupt rationale, TripAdvisor traceability decision, bonus patterns explicitly labeled
- Bonus points gap (15/25 → higher): human-in-the-loop interrupt, multi-source rating comparison, 10-query GraphRAG vs. vector table — need to be *explicitly labeled* as advanced techniques in submission doc

---

## What to build next session (Phase 3 + 4, complete build)

Full plan saved at: `/Users/ayyaswamy/.claude/plans/purrfect-inventing-snail.md`

### Build order

#### Layer 1 — `routeiq/ratings/base.py`
```python
@dataclass
class RatedPOI:
    poi: POI
    rating: float | None = None
    review_count: int | None = None
    review_snippet: str | None = None
    all_snippets: list[str] | None = None    # NEW — up to 3 TripAdvisor reviews
    review_source: str | None = None         # NEW — "TripAdvisor" | "Foursquare"
    hours: str | None = None
    photo_urls: list[str] | None = None      # NEW — up to 5 photos

class POIRatingProvider(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str: ...        # NEW
    @abstractmethod
    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]: ...
```

#### Layer 2 — existing provider updates
- `FoursquareRatingProvider`: add `source_name = "Foursquare"`; add `review_source=self.source_name` to `RatedPOI(...)` in `_make_rated`
- `GooglePlacesRatingProvider`: add `source_name = "Google Places"`
- `_NullRatingProvider` (in factory.py): add `source_name = "Unknown"`

#### Layer 3 — `routeiq/ratings/tripadvisor.py` (new, full implementation)

```
source_name = "TripAdvisor"
API base: https://api.content.tripadvisor.com/api/v1
Auth: key={api_key} as query param (NOT Authorization header like Foursquare)

enrich_batch(city, pois):
  1. centroid = avg(poi.lat), avg(poi.lon)
  2. pool = _fetch_nearby(city, centroid_lat, centroid_lon)   → 1 API call, cached 21 days
  3. ChromaDB index on pool names (same uuid4 pattern as Foursquare)
  4. For each POI: _find_match() → name similarity + 100m proximity fallback
  5. For matched POIs: _fetch_reviews(location_id) + _fetch_photos(location_id)
  6. Return RatedPOI(all_snippets=[...], review_source="TripAdvisor", photo_urls=[...])

_fetch_nearby(city, lat, lon):
  GET /location/nearby_search?key=&latLong={lat},{lon}&category=attractions
                              &radius=15&radiusUnit=km&language=en
  cache: cache/ratings/tripadvisor_{safe_city}_pool.json (21 days)
  Response fields: location_id, name, latitude, longitude, rating, num_reviews

_fetch_reviews(location_id):
  GET /location/{id}/reviews?key=&language=en
  cache: cache/ratings/tripadvisor_review_{location_id}.json (21 days)
  Extract: data[*].text → all_snippets (up to 3)

_fetch_photos(location_id):
  GET /location/{id}/photos?key=&language=en
  cache: cache/ratings/tripadvisor_photos_{location_id}.json (21 days)
  Extract: data[*].images.large.url (fallback: medium → small) → photo_urls (up to 5)

Rating: TripAdvisor returns 1–5 scale — NO ÷2 needed (unlike Foursquare's 0–10)
```

#### Layer 4 — `routeiq/ratings/factory.py`
Add tripadvisor routing block (same pattern as foursquare). Default env var stays `foursquare`
— user sets `RATING_PROVIDER=tripadvisor` in their own `.env`.

#### Layer 5 — `routeiq/agent/tools/rate_pois.py`
In the `results.append(entry)` block add:
```python
entry["review_source"] = rp.review_source
entry["all_snippets"] = rp.all_snippets or []
entry["photo_urls"] = rp.photo_urls or []
```

#### Layer 6 — `routeiq/insights/prompts/day_trip_planner.py`
`DAY_TRIP_PLANNER_PROMPT_V1` — see stop JSON shape above.

Key prompt rules:
- Tool call order: find_city_pois → rate_pois → enrich_poi_details (top 8) → estimate_visit + get_travel_time → JSON output
- `visitor_quote`: pick catchiest from `all_snippets`, prefix with `review_source`
- `activities`: derive from Wikipedia description AND provider snippets only; OSM subtype fallback for silent POIs
- `why_visit`: Wikipedia only — factual, one sentence
- Schedule in geographic order
- Output ONLY the JSON block — no markdown fences, no commentary

#### Layer 7 — `routeiq/agent/day_trip_agent.py`

```
Nodes:
  plan   — manual ReAct loop: llm.bind_tools(ALL_TOOLS) + while tool_calls: execute
            First call: inject DAY_TRIP_PLANNER_PROMPT messages
            Re-plan: state["messages"] already has history + feedback HumanMessage
  review — interrupt(state["draft_itinerary"]); returns {"approved": bool, "feedback": str}
            On approved=False: appends HumanMessage("Refine itinerary: {feedback}") to state
  narrate— llm.invoke(state["messages"] + [HumanMessage("Write warm 3-4 sentence narrative:")])

Edges: START → plan → review → narrate (approved=True) | plan (approved=False)
Checkpointer: MemorySaver()

_parse_draft(content: str) -> dict | None
  Strips ```json fences, finds outermost { } by brace-depth counting, json.loads
```

#### Layer 8 — `routeiq/agent/__init__.py`
Add: `from routeiq.agent.day_trip_agent import build_day_trip_graph`
Update `__all__`.

#### Layer 9 — Tests

**`tests/ratings/test_tripadvisor.py`** (10 tests):
- pool cache hit / miss / stale
- reviews cached per location_id
- photos cached per location_id
- rating passthrough (no ÷2)
- all_snippets populated from 3 reviews
- photo_urls populated from 5 photos (large → medium fallback)
- name similarity match
- proximity fallback ≤ 100m
- review_source always = "TripAdvisor"
- empty pool → NullRatedPOI with review_source set

**`tests/agent/test_day_trip_agent.py`** (4 tests):
- Mock LLM: `bind_tools` returns self; `invoke` returns `AIMessage(content=json.dumps(draft))`
  with `tool_calls=[]` — exits ReAct loop on first call
- `test_interrupt_fires`: stream initial state → `graph.get_state(config).next` contains `"review"`
- `test_resume_approved_reaches_narrate`: `Command(resume={"approved": True})` → narrate node called → `state["narrative"]` is set
- `test_resume_refine_loops_plan`: `Command(resume={"approved": False, "feedback": "..."})` → plan called again → new `draft_itinerary`
- `test_parse_draft_strips_fences`: `_parse_draft("```json\n{...}\n```")` returns dict

#### Layer 10 — `app.py` two-tab UI

```python
tab1, tab2 = st.tabs(["🏙 Day Trip Planner", "🗺 Route Planner"])
# tab2 = all existing Route Planner code (unchanged)
# tab1 = Day Trip Planner:
```

Day Trip Planner tab structure:
1. **Inputs**: city text_input, preferences multiselect (nature/history/food/art), hours slider (4–12), start_time selectbox
2. **Pre-flight KG check**: `kg.known_cities()` → if city not in set: `st.spinner("Fetching POIs for {city}...")` + `kg.add_city_pois()`
3. **Chat UI**: `st.chat_input` + `st.chat_message` history
4. **Agent streaming**: tool call expander shows tool name + result summary
5. **Interrupt rendering**: draft stop cards with time slots, TripAdvisor photo, visitor_quote, activities
6. **Approve button**: `graph.invoke(Command(resume={"approved": True}), config=...)`
7. **Refine**: text_input + button → `Command(resume={"approved": False, "feedback": text})`
8. **Post-approval**: `st.markdown(narrative)` + Folium map (numbered stop markers, 1 per stop)

KG + graph cached with `@st.cache_resource`. `thread_id` = UUID stored in `st.session_state`.

#### Layer 11 — `scripts/seed_ratings_cache.py`

```python
DEMO_CITIES = [
    ("San Francisco, CA", 37.7749, -122.4194),
    ("Napa, CA", 38.2975, -122.2869),
    ("San Jose, CA", 37.3382, -121.8863),
    ("Half Moon Bay, CA", 37.4636, -122.4286),
    ("Sausalito, CA", 37.8591, -122.4853),
]
```
Runs both `FoursquareRatingProvider` + `TripAdvisorRatingProvider` per city.
Uses KG POIs for that city as the input POI list (triggers pool cache + per-POI caches).
Skips providers with missing keys. Prints progress.

#### Layer 12 — `.env.example` fix
Remove duplicate `RATING_PROVIDER` line. Add `TRIPADVISOR_API_KEY=` under a new TripAdvisor block.

#### Layer 13 — Scope definition docs
- `docs/scope-definition.md` — NEW 1-page scope doc for submission
- `docs/agent-architecture.md` — add Scope section, label bonus patterns explicitly

---

## Verification checklist (run at end of next session)

1. `python3 -m pytest tests/ -v` — all 166+ tests pass (expect ~180)
2. `streamlit run app.py` → two tabs: **"Day Trip Planner"** first, "Route Planner" second
3. Route Planner tab: existing 5 demo routes work (no regression)
4. Day Trip tab — Bay Area: "Plan scenic day in San Francisco — nature and history, 8 hours at 9am"
   - No KG spinner (SF already in KG)
   - Tool calls stream in expander
   - Stop cards show TripAdvisor photo + visitor_quote + activities
   - Approve → narrative + map renders
5. Day Trip tab — non-Bay-Area: "Plan a day in Los Angeles, CA"
   - Spinner: "Fetching POIs for Los Angeles..."
   - After fetch: agent starts, same flow
   - Second run: no spinner (KG cached in session)
6. Refine flow: feedback → agent re-plans
7. `ls cache/ratings/` → tripadvisor_*.json files present
8. `python3 scripts/seed_ratings_cache.py` → 15 TripAdvisor + 15 Foursquare pool files
9. `docs/scope-definition.md` exists and has problem statement + in/out-of-scope list

---

## Key gotchas from design (carry forward)

- TripAdvisor auth: `key={api_key}` as **query param** — NOT `Authorization` header like Foursquare
- TripAdvisor rating scale: **1–5 already** — no ÷2 normalization (Foursquare returns 0–10)
- TripAdvisor lat/lon in pool response: string fields (`"37.8199"`) — must `float()` before haversine
- `_NullRatingProvider` also needs `source_name = "Unknown"` to satisfy ABC
- `all_snippets` is `list[str] | None` — rate_pois tool outputs `[]` when None (JSON-safe)
- `photo_urls` is `list[str] | None` — stop card falls back to `image_url` (Wikipedia) when empty
- Tab order: Day Trip Planner = tab index 0 (first), Route Planner = tab index 1

---

## Git state

- Branch: `feature/routeiqagent`
- Last commit: 7c6e8fe (feat: add ratings layer + agent tools + KG dynamic city expansion)
- 166/166 tests passing
- Nothing to commit this session (planning only)
