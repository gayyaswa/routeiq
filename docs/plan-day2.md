# Day 2 — Routing Layer + LangGraph Pipeline

## Goal
Build the routing layer (detour scoring, POI selection), all LangChain chains (query parser,
narrative, fallback), the LangGraph state machine, and the Facade entry point.
End state: a full NL query → route → POIs → Claude narrative pipeline, with stub LLM
fallback when no API key is present.

---

## Files created

```
routeiq/routing/
  scored_poi.py         ScoredPOI dataclass
  detour_scorer.py      DetourScorer (Strategy)
  poi_selector.py       POISelector (Strategy)
  __init__.py           re-exports

routeiq/insights/
  query_parser.py       QueryParser (Chain)
  narrative_chain.py    NarrativeChain (Chain)
  fallback_chain.py     FallbackChain (Chain)
  prompts/
    __init__.py         re-exports active prompts
    system.py           SYSTEM_PROMPT (global persona + faithfulness rules)
    query_parser.py     QUERY_PARSER_PROMPT_V1
    narrative.py        NARRATIVE_PROMPT_V1
    fallback.py         FALLBACK_PROMPT_V1
  examples/
    __init__.py
    query_parser_examples.py   FEW_SHOT_EXAMPLES list
  __init__.py

routeiq/pipeline.py     RoutePipeline + PipelineState (LangGraph)
routeiq/facade.py       RouteIQFacade (Facade + DI)

tests/
  test_detour_scorer.py
  test_poi_selector.py
  test_query_parser.py
  test_narrative_chain.py
  test_fallback_chain.py
  test_pipeline.py

day2_verify.py
```

---

## Step 1 — Routing layer (pure Python, no LLM)

### `routeiq/routing/scored_poi.py`
```python
@dataclass
class ScoredPOI:
    poi: POI
    detour_km: float
    detour_min: float
```

### `routeiq/routing/detour_scorer.py` — DetourScorer (Strategy)
- `score(pois, route_coords) → list[ScoredPOI]`
- For each POI: `min_dist = min(haversine(poi, coord) for coord in route_coords)`
- `detour_km = 2.0 * min_dist` (round trip to POI and back)
- `detour_min = (detour_km / avg_speed_kmh) * 60`
- Uses haversine — same formula as RouteGraph heuristic

### `routeiq/routing/poi_selector.py` — POISelector (Strategy)
- `select(scored_pois, preferences) → list[ScoredPOI]`
- Filter by category if preferences provided; silent fallback to all POIs if no match
- Sort by `detour_min` ascending, return top-N (default 5)

### `routeiq/routing/__init__.py`
```python
from routeiq.routing.scored_poi import ScoredPOI
from routeiq.routing.detour_scorer import DetourScorer
from routeiq.routing.poi_selector import POISelector
```

---

## Step 2 — Prompt registry

### `routeiq/insights/prompts/system.py`
```python
SYSTEM_PROMPT = """You are a scenic route assistant that recommends landmarks and stops along a driving route.

Rules:
- Only recommend stops that are spatially verified along the route by the graph layer.
- Never invent or hallucinate landmarks. If context is empty, say so explicitly.
- Keep recommendations concise: name, why visit, estimated detour time.
- If you cannot parse the query or find relevant stops, say so clearly — do not guess.
"""
```

### `routeiq/insights/prompts/query_parser.py` — QUERY_PARSER_PROMPT_V1
```
System: SYSTEM_PROMPT
Human:
  Extract the route intent from the query below.
  Few-shot examples: {examples}
  Return JSON with keys: origin, destination, preferences (list of strings).
  If any field cannot be determined, set it to null.
  Query: {query}
```

### `routeiq/insights/examples/query_parser_examples.py`
```python
FEW_SHOT_EXAMPLES = [
    {
        "query": "Drive from Austin to San Antonio, show me historic towns and natural springs",
        "output": '{"origin": "Austin, TX", "destination": "San Antonio, TX", "preferences": ["historic", "natural"]}',
    },
    {
        "query": "Road trip from Houston to Dallas with scenic stops",
        "output": '{"origin": "Houston, TX", "destination": "Dallas, TX", "preferences": ["scenic"]}',
    },
    {
        "query": "take me somewhere interesting",
        "output": '{"origin": null, "destination": null, "preferences": []}',
    },
]
```

### `routeiq/insights/prompts/narrative.py` — NARRATIVE_PROMPT_V1
```
System: SYSTEM_PROMPT
Human:
  Origin: {origin}, Destination: {destination}
  Distance: {distance_km} km, Drive time: {drive_time_min} min
  Recommended stops: {poi_context}
  Write 3-5 sentence narrative + stop list (name | detour time | why visit)
```

### `routeiq/insights/prompts/fallback.py` — FALLBACK_PROMPT_V1
```
System: SYSTEM_PROMPT
Human:
  The query "{query}" could not be fully answered.
  Reason: {reason}
  Respond helpfully and briefly. Suggest what a valid query looks like.
```

### `routeiq/insights/prompts/__init__.py`
```python
from routeiq.insights.prompts.query_parser import QUERY_PARSER_PROMPT
from routeiq.insights.prompts.narrative import NARRATIVE_PROMPT
from routeiq.insights.prompts.fallback import FALLBACK_PROMPT
```

---

## Step 3 — LangChain chains

### `routeiq/insights/query_parser.py` — QueryParser (Chain)
```python
class QueryParser:
    def __init__(self, prompt, llm):
        self._chain = prompt | llm | StrOutputParser()

    def parse(self, query: str) -> dict:
        raw = self._chain.invoke({"examples": ..., "query": query})
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"origin": None, "destination": None, "preferences": [], "_parse_error": str(e)}
        result.setdefault("origin", None)
        result.setdefault("destination", None)
        result.setdefault("preferences", [])
        return result
```
Key: `_parse_error` key signals parse failure to the pipeline — no exception raised.

### `routeiq/insights/narrative_chain.py` — NarrativeChain (Chain)
```python
class NarrativeChain:
    def __init__(self, prompt, llm):
        self._chain = prompt | llm | StrOutputParser()

    def generate(self, origin, destination, distance_km, drive_time_min, top_pois,
                 *, poi_context: str | None = None) -> str:
        # poi_context kwarg added in Day 3 — backward compatible
        return self._chain.invoke({
            "origin": origin, "destination": destination,
            "distance_km": f"{distance_km:.1f}",
            "drive_time_min": f"{drive_time_min:.0f}",
            "poi_context": poi_context if poi_context else self._format_poi_context(top_pois),
        })

    @staticmethod
    def _format_poi_context(top_pois) -> str:
        if not top_pois:
            return "No scenic stops found along this route."
        return "\n".join(
            f"{sp.poi.name} ({sp.poi.category}) — {sp.detour_km:.1f} km detour, {sp.detour_min:.0f} min"
            for sp in top_pois
        )
```

### `routeiq/insights/fallback_chain.py` — FallbackChain (Chain)
```python
class FallbackChain:
    def __init__(self, prompt, llm):
        self._chain = prompt | llm | StrOutputParser()

    def generate(self, reason: str, query: str) -> str:
        return self._chain.invoke({"reason": reason, "query": query})
```

### `routeiq/insights/__init__.py`
```python
from routeiq.insights.query_parser import QueryParser
from routeiq.insights.narrative_chain import NarrativeChain
from routeiq.insights.fallback_chain import FallbackChain
```

---

## Step 4 — LangGraph pipeline

### `routeiq/pipeline.py` — PipelineState + RoutePipeline

**PipelineState (TypedDict):**
```python
class PipelineState(TypedDict):
    query: str
    origin: Optional[str]
    destination: Optional[str]
    preferences: Optional[list[str]]
    origin_lat: Optional[float]; origin_lon: Optional[float]
    dest_lat: Optional[float];   dest_lon: Optional[float]
    route_result: Optional[Any]
    pois: Optional[list[Any]]
    top_pois: Optional[list[Any]]
    poi_context: Optional[str]
    narrative: Optional[str]
    error: Optional[str]
    fallback_reason: Optional[str]
```

**Graph structure:**
```
parse ──conditional──► graph ──conditional──► rag ──conditional──► narrate → END
  └──error──────────────────────────────────────────────────────────►
```

**Conditional edge logic:**
- After parse: `error or no origin or no destination` → narrate (fallback)
- After graph: `error` → narrate (fallback)
- After rag: always → narrate

**Error codes:**
| Code | When set |
|------|---------|
| `unparseable_query` | `_parse_error` key in QueryParser result |
| `geocode_failed` | `ox.geocode()` raises exception |
| `route_not_found` | `nx.NetworkXNoPath` via `RouteGraph.find_route()` |
| `route_too_long` | `route_result.drive_time_min > 360` (6 hours) |
| `no_pois_found` | `top_pois` is empty in `_rag_node` |

**`_graph_node` key steps:**
1. `ox.geocode(origin)` and `ox.geocode(destination)` → lat/lon
2. Compute bbox with 0.1 degree padding
3. `GraphLoader.load(north, south, east, west)`
4. `RouteGraph(G).find_route(...)` → RouteResult
5. Check `drive_time_min > 360` → route_too_long
6. `POIFinder.find_pois(route_result.route_coords)` → pois
7. `DetourScorer.score(pois, route_coords)` → scored
8. `POISelector.select(scored, preferences)` → top_pois

**`_rag_node` (Day 2 stub, filled in Day 3):**
```python
def _rag_node(self, state):
    if not state.get("top_pois"):
        return {"error": "no_pois_found", "fallback_reason": "..."}
    return {}  # stub — Day 3 fills this
```

**`_narrate_node`:**
```python
def _narrate_node(self, state):
    if state.get("error"):
        narrative = self._fallback_chain.generate(
            reason=state.get("fallback_reason", state["error"]),
            query=state["query"],
        )
    else:
        narrative = self._narrative_chain.generate(
            origin=state["origin"], destination=state["destination"],
            distance_km=state["route_result"].length_km,
            drive_time_min=state["route_result"].drive_time_min,
            top_pois=state.get("top_pois") or [],
            poi_context=state.get("poi_context"),   # added Day 3
        )
    return {"narrative": narrative}
```

---

## Step 5 — Facade

### `routeiq/facade.py` — RouteIQFacade (Facade + DI)
```python
class RouteIQFacade:
    def __init__(self, llm, *, graph_loader=None, poi_finder=None,
                 detour_scorer=None, poi_selector=None,
                 wikipedia_fetcher=None, poi_indexer=None, poi_retriever=None):
        self._pipeline = RoutePipeline(
            query_parser=QueryParser(QUERY_PARSER_PROMPT, llm),
            graph_loader=graph_loader or GraphLoader(),
            poi_finder=poi_finder or POIFinder(),
            detour_scorer=detour_scorer or DetourScorer(),
            poi_selector=poi_selector or POISelector(),
            narrative_chain=NarrativeChain(NARRATIVE_PROMPT, llm),
            fallback_chain=FallbackChain(FALLBACK_PROMPT, llm),
            wikipedia_fetcher=wikipedia_fetcher or WikipediaFetcher(),
            poi_indexer=_indexer,
            poi_retriever=poi_retriever or POIRetriever(_indexer),
        )

    def run(self, query: str) -> dict:
        return self._pipeline.run(query)
```
DI for all components: each is optional and defaults to production instance.
Allows tests to inject mocks without touching any internal class.

---

## Step 6 — Tests

**`test_detour_scorer.py`** (9 tests)
- empty pois/route → []
- poi on route → near-zero detour
- `detour_km == 2 * nearest_dist`
- `detour_min == (detour_km / 50) * 60`
- returns ScoredPOI instances
- haversine: same point → 0, Austin→SA ~120km, symmetry

**`test_poi_selector.py`** (8 tests)
- empty → []
- preference match filters correctly
- no preference match → silent fallback to all
- no preferences → all scored
- sorted by detour_min ascending
- top_n cap respected
- default top_n=5

**`test_query_parser.py`** (8 tests)
- valid JSON → dict with origin/destination/preferences
- `_parse_error` key on bad JSON
- null fields defaulted
- preferences extracted as list
- mock LLM via `RunnableLambda`

**`test_narrative_chain.py`** (6 tests)
- returns string, not empty
- poi_context kwarg used when provided
- `_format_poi_context` with empty list → "No scenic stops..."
- name/category/detour in formatted context

**`test_fallback_chain.py`** (3 tests)
- returns string
- not empty
- reason passed to chain invocation

**`test_pipeline.py`** (17 tests — updated in Day 3)
- parse node: success/error paths
- route_after_parse: all 4 outcomes
- graph node: success, geocode_failed, route_not_found, route_too_long
- route_after_graph: rag / narrate
- rag node: no_pois_found, with_pois (Day 3 updates this)
- narrate node: error path calls fallback, success calls narrative

---

## Step 7 — day2_verify.py

Stub LLM fallback when no ANTHROPIC_API_KEY:
```python
def _stub_llm():
    def respond(msgs):
        human_text = next((m.content for m in msgs.messages if isinstance(m, HumanMessage)), "")
        if "Extract the route intent" in human_text:
            return AIMessage(content='{"origin": "Austin, TX", "destination": "San Antonio, TX", "preferences": ["historic"]}')
        if "could not be fully answered" in human_text:
            return AIMessage(content="I couldn't find a route for your query...")
        return AIMessage(content="This scenic drive from Austin to San Antonio...")
    return RunnableLambda(respond)
```

Runs two paths:
1. Happy path: `"Drive from Austin to San Antonio, show me historic towns and natural springs"`
2. Fallback path: `"take me somewhere interesting"` (no origin/destination)

---

## Key gotchas

| Gotcha | Detail |
|--------|--------|
| `ox.geocode` patch path | Patch at `"osmnx.geocode"` — that's where pipeline imports it |
| `RouteGraph` patch path | Patch at `"routeiq.pipeline.RouteGraph"` |
| `RunnableLambda` for mock LLM | No `spec=` needed — accepts any input |
| `_parse_error` vs exception | QueryParser never raises — always returns dict with `_parse_error` key |
| Preferences fallback | POISelector silently falls back to all POIs if no category matches preferences |
| Route too long threshold | `_ROUTE_TOO_LONG_MIN = 360.0` (6 hours) — defined at module level in pipeline.py |

---

## Verification

```bash
python3 -m pytest tests/ -v      # 73 tests passing (Days 1+2)
python3 day2_verify.py           # works with or without ANTHROPIC_API_KEY
```
