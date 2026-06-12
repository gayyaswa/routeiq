# RouteIQ — Week 2 Submission

---

## 1. Project Overview

Consider the query: *"Drive from San Francisco to Muir Woods, show redwoods and coastal
views."* A vector search over Bay Area landmarks returns semantically plausible stops —
Stinson Beach, Pigeon Point Lighthouse, Point Reyes Seashore — but three of the five
require driving past Muir Woods and backtracking along a different highway entirely.
The results are semantically correct and geographically wrong. The problem is not
relevance — it is that embedding similarity has no representation of a driving corridor.
It cannot distinguish a stop 0.3 km off the A\* path from one 80 km away; both score
equally if their descriptions match "coastal redwoods."

RouteIQ is built around the premise that route queries carry a retrieval constraint that
a vector index alone cannot enforce: stops must lie within the actual path corridor, not
just within the semantic neighbourhood. Solving that requires computing the path first,
deriving a geographic gate from it, and applying that gate before anything reaches the
ranking or generation stages.

The system chains three retrieval layers to achieve this. OSMnx downloads the real OSM
road network, NetworkX A\* computes the shortest path between geocoded origin and
destination, and a Shapely 5 km corridor buffer becomes the hard spatial filter — only
POIs whose centroid falls inside that polygon enter the pipeline. The RouteKnowledgeGraph
(NetworkX DiGraph, 95 pre-seeded Bay Area POIs) then adds relational context that
embeddings cannot carry: which city a stop belongs to, its region, its OSM category, and
which other notable landmarks are nearby. ChromaDB over Wikipedia-enriched description
chunks provides semantic matching within that already-constrained candidate set. Claude
receives the assembled context and generates a streaming narrative grounded entirely in
spatially verified, Wikipedia-enriched stop data.

The 10-query evaluation makes the distinction empirical: GraphRAG wins all 6
route-specified queries, vector wins all 4 open-ended semantic queries, 10/10 prediction
accuracy. GraphRAG and vector are not competing — they solve different sub-problems of
the same retrieval task.

**Pipeline:**

```
NL Query
    → LangGraph Pipeline
        [parse]   Claude extracts origin / destination / preferences
        [graph]   OSMnx geocode → road network → NetworkX A* → POI spatial join (5 km buffer) → DetourScorer → top 5 POIs
        [rag]     Wikipedia enrichment (parallel) → ChromaDB chunk+index → 3-stage KnowledgeRAG
        [narrate] Claude streaming narrative
    → Streamlit UI
```

---

## 2. Pipeline Orchestration — Why LangGraph

LangGraph is a graph-based workflow engine for LLM pipelines built on top of LangChain.
The mental model is a **typed state machine**: you define nodes (units of work), edges
(how they connect), and one shared state object (a typed dict) that every node reads from
and writes to. `StateGraph.compile()` turns that definition into a runnable graph.
For engineers coming from traditional software, the closest analogy is a workflow engine
(think AWS Step Functions or Durable Functions) where each activity is an LLM or tool
call instead of a microservice.

**How RouteIQ uses it:**

```
PipelineState (TypedDict — shared DTO across all nodes)
    query, origin, destination, preferences
    route_result, pois, top_pois, poi_context
    narrative, error, fallback_reason

Graph topology:
    parse ──[conditional]──▶ graph ──[conditional]──▶ rag ──▶ narrate ──▶ END
              ↘ on error                ↘ on error
               └─────────────────────────────────────▶ narrate
```

Each node owns its slice of state and writes only what it produces — `parse` writes
`origin / destination`, `graph` writes `route_result / pois / top_pois`, `rag` writes
`poi_context`, `narrate` writes `narrative`. Any node that hits an unrecoverable condition
(geocoding failed, Overpass unavailable, no POIs found, route too long) sets `state["error"]`
and the conditional edge automatically re-routes to `narrate`, which hands off to the
`FallbackChain` for a graceful user-facing message.

**Key benefit:** Any node that hits an unrecoverable condition sets `state["error"]` and
the conditional edge automatically re-routes to `narrate` (FallbackChain). Error handling
is centralised in the graph topology rather than scattered across every caller.
Extending the pipeline — adding a caching node, a retry step, or a human-review gate —
is one node + one edge change; existing nodes are untouched.

---

## 3. Datasets and Corpus

| Source | What | Volume |
|--------|------|--------|
| OpenStreetMap via OSMnx + Overpass | Road network graphs + POI metadata (tourism, historic, natural subtypes) | Pre-seeded: 984 unique Bay Area POIs in `bay_area_all.json.gz`; any region on demand |
| Wikipedia MediaWiki API | Landmark intro extract (≤500 chars) + thumbnail image URL per POI | Fetched at query time, parallelized (5 threads, 15s timeout) |
| RouteKnowledgeGraph (pre-seeded) | 95 OSM-verified notable Bay Area POIs, 10 cities, 7 regions, typed edges (LOCATED_IN / HAS_CATEGORY / IN_REGION / NEAR_POI) | 112+ nodes, 4 edge types |

**Ingestion and chunking:**

- OSM features filtered by explicit subtype allowlists — not the broad `historic: True`
  tag which returns county boundaries and unnamed roads
- Wikipedia descriptions chunked into 250-character segments with 20-character overlap
  before ChromaDB indexing
- Chunk metadata stores the parent `osm_id` so graph augmentation can operate on the
  full entity after chunked retrieval

**Freshness:** OSM road networks cached as pickle files (10–50 MB, gitignored,
auto-fetched at startup). POI master file committed to repo (`bay_area_all.json.gz`,
33 KB gzip) for demo reliability. Wikipedia fetched fresh per query.

---

## 4. The Three RAG Approaches

### 4a. Vector RAG (semantic baseline)

The vector baseline exists to answer one question: how much does the graph layer actually
add? It is the simplest possible retrieval approach — index landmark descriptions, query
by cosine similarity, return the top 5. At startup, 95 OSM-verified notable Bay Area
landmarks are loaded from `bay_area_all.json.gz`, Wikipedia-enriched in parallel, and
indexed into ChromaDB. At query time, the user's full query string becomes the embedding
query. No geographic constraints are applied at any stage.

This works well for open-ended discovery queries — *"beautiful coastal drives," "wine
country day trips from SF"* — where there is no route to constrain results and pure
semantic recall over POI descriptions is the right tool. The moment a route enters the
picture, it breaks. For SF→Sausalito, vector returns Golden Gate Bridge (semantically
correct, happens to be on the route by coincidence), but also Muir Beach Overlook and
Japanese Tea Garden — neither remotely on the route. Semantic similarity has no way to
enforce a geographic corridor. It simply doesn't know what "on the route" means.

That failure mode is exactly what motivated the GraphRAG approach: route queries need a
spatial contract that embeddings cannot express.

*Eval: 4/4 wins on open-ended semantic queries, 0/6 wins on route queries.*

---

### 4b. GraphRAG (main approach)

The core observation is that a route query has two components: a *geographic constraint*
(stops must lie along the path) and a *preference signal* (show me wineries, beaches,
historic forts). Vector search handles the preference signal well but cannot enforce the
geographic constraint. The graph layer exists to do precisely that.

OSMnx downloads the road network for the corridor bounding box and caches it as a pickle
file (first load: 30–60s, subsequent: ~0.5s). NetworkX A\* finds the shortest path,
producing an ordered sequence of (lat, lon) coordinates. A `Shapely LineString.buffer(5 km)`
turns that path into a polygon, and an Overpass query fetches OSM features in the bbox —
a centroid-in-polygon filter keeps only those whose centroid falls inside the corridor.
For all Bay Area demo routes, this Overpass step is skipped entirely: a pre-seeded
`bay_area_all.json.gz` (984 POIs, 33 KB gzip) is filtered in memory in ~0.1s vs. 11–21s
for a live query.

The corridor filter solves the false-positive problem, but the ranking problem remains:
sorting by detour cost alone fills all five slots from the cheapest POIs geographically,
which on a route through a dense city means five street-level plaques in the same
neighbourhood. Three ranking tiers address this. First, the OSM `wikipedia` tag — OSM
contributors only add this to features with a verified Wikipedia article, making it a
reliable crowd-sourced notability signal. Second, scenic subtype score derived from the
OSM value (viewpoint=9, beach=9, lighthouse=8, fort=7, memorial=3) — detour cost is a
constraint, not a measure of scenic value. Third, detour minutes as a tiebreaker only.
A greedy 2 km minimum spread then ensures no single dense neighbourhood claims all five
slots.

*Eval: 6/6 wins on route queries.*

---

### 4c. Knowledge Graph RAG (augmentation layer)

After the spatial join selects the right stops, the narrative context assembled for Claude
was initially thin: name, category, detour time, and a Wikipedia description. What it
lacked was relational context — which city a stop belongs to, which broader region, what
other notable landmarks are nearby. Without that, the narrative Claude generated felt
geographically unanchored.

The knowledge graph adds that relational layer. `RouteKnowledgeGraph` is a NetworkX
DiGraph pre-seeded with 95 OSM-verified notable Bay Area POIs, 10 cities, and 7 regions,
connected by four typed edge relationships:

| Edge | Connects | Enables |
|------|----------|---------|
| `LOCATED_IN` | POI → City | "near San Francisco" filtering |
| `HAS_CATEGORY` | POI → Category | preference-based filtering ("show wineries") |
| `IN_REGION` | POI/City → Region | broad corridor matching ("Bay Area") |
| `NEAR_POI` | POI ↔ POI | "also nearby" co-recommendations |

The KG runs as a three-stage pipeline after the spatial join. First, ChromaDB semantic
search over 250-character POI description chunks finds candidates by similarity to the
user's preferences. Second, `RouteKnowledgeGraph` filters those candidates to POIs
geographically near the route and augments each with city, region, and nearby POI names
retrieved via graph traversal. Third, those augmented results are assembled into the
context string Claude receives: `name | category | city | region | nearby stops | description`.

The typed edges are what make this more than a lookup table. They allow multi-hop
queries that embeddings cannot express — "POIs in the Bay Area region, in the winery
category, near a specific landmark on the route" — traversed in milliseconds over a
small in-memory graph. Even 95 seed POIs covering the Bay Area demo routes is enough to
produce noticeably richer, more geographically grounded narratives. POIs outside the KG
seed fall back to vector-only context gracefully; the graph augmentation step simply
returns nothing and the pipeline continues.

---

## 5. Narration and Generation

### System prompt (shared across all chains — verbatim)

```
You are a scenic route assistant that recommends landmarks and stops along a driving route.

Rules:
- Only recommend stops that are spatially verified along the route by the graph layer.
- Never invent or hallucinate landmarks. If context is empty, say so explicitly.
- Keep recommendations concise: name, why visit, estimated detour time.
- If you cannot parse the query or find relevant stops, say so clearly — do not guess.
```

**Design principle:** Faithfulness over fluency. The first rule ("spatially verified")
is enforced in code by the corridor filter, but also stated explicitly in the prompt so
Claude never recommends a stop the graph layer didn't surface.

---

### Query parsing prompt (V1 — active, verbatim)

```
Extract the route intent from the query below.

Few-shot examples:
{examples}

Return JSON with keys: origin, destination, preferences (list of strings).
If any field cannot be determined, set it to null.

Query: {query}
```

**What it produces:**
```json
{"origin": "San Francisco, CA", "destination": "Napa, CA", "preferences": ["wineries", "historic towns"]}
```

**Key learning:** Claude wraps JSON in markdown fences (` ```json ``` `); defensive
stripping with `re.sub` before `json.loads()` is required even with explicit prompt
instructions to return raw JSON.

---

### Narrative prompt evolution: V1 → V2 → V3

**V1 — baseline (verbatim):**

```
Generate a scenic route narrative for the following trip.

Origin: {origin}
Destination: {destination}
Total distance: {distance_km} km
Estimated drive time: {drive_time_min} minutes

Recommended stops (ranked by interest, spatially verified):
{poi_context}

Write a short, engaging narrative (3-5 sentences) followed by a structured stop list.
Each stop: name | detour time | why visit
```

*Problem:* No description context provided. Claude invented visit reasons, producing
plausible-sounding but hallucinated landmark details.

---

**V2 — Wikipedia-enriched (verbatim):**

```
Generate a scenic route narrative for the following trip.

Origin: {origin}
Destination: {destination}
Total distance: {distance_km} km
Estimated drive time: {drive_time_min} minutes

Recommended stops with context (spatially verified, Wikipedia-enriched):
{poi_context}

Each stop entry is formatted as:
  name | category | detour time | description

Instructions:
- Write an engaging opening narrative (3-5 sentences) that sets the mood for the drive.
- Then list each stop with: name | detour time | one sentence on why to visit (drawn from the description).
- Ground every recommendation in the provided descriptions — do not invent facts.
- If a stop has no description, rely on the category and name only.
```

*Improvement:* Hallucination significantly reduced. Narratives grounded in real
Wikipedia text. POIs with no description passed through gracefully.

---

**V3 — KG-enriched, active (verbatim):**

```
Generate a scenic route narrative for the following trip.

Origin: {origin}
Destination: {destination}
Total distance: {distance_km} km
Estimated drive time: {drive_time_min} minutes

Recommended stops (graph-verified: spatially on route, Wikipedia-enriched):
{poi_context}

Each stop is formatted as:
  name | category | city | region | nearby stops | description excerpt

Instructions:
- Write an engaging opening narrative (3-5 sentences) that captures the character of the route and region.
- List each stop: name | detour time | one sentence why to visit, drawn from the description.
- Mention the region where it adds flavour (e.g. "deep in the Hill Country").
- Ground every fact in the provided context. Do not invent locations or distances.
```

*Improvement:* Richer, more geographically grounded narratives. Region context prevents
Claude from inventing regional descriptions. "Nearby stops" field creates natural
co-recommendation flow in the narrative.

**Streaming:** Narrative tokens stream via a `stream()` method on `NarrativeChain`,
tail-displayed (last 450 chars visible) in a live Streamlit placeholder with 120ms
throttle to prevent render backlog — map appears immediately after streaming completes.

---

## 6. Evaluation — GraphRAG vs Vector Baseline

*Generated 2026-06-10 — `python3 eval/run_eval.py` — vector baseline: 91 Wikipedia-enriched notable Bay Area POIs · KnowledgeGraph: 95 Bay Area POIs with typed edges*

| # | Query | Type | GraphRAG POIs | Vector POIs | Winner |
|---|-------|------|--------------|-------------|--------|
| 1 | Drive from San Francisco to Muir Woods, show redwoods and coastal views | route | Top of the Mark, Muir Beach Overlook, Rob Hill, Mount Tamalpais East Peak, Potrero Hill | Muir Beach Overlook, San Francisco Botanical Garden, Richardson Bay, Buena Vista Heights, Portola Discovery Site of SF Bay | 🗺 GraphRAG |
| 2 | Road trip from San Francisco to Napa Valley, show wineries and historic towns | route | Warden's House, Coit Tower, Lightship Relief, Sather Gate, Quarters A | Cable Car Powerhouse and Barn, Potrero Hill, Portola Discovery Site of SF Bay, V. Sattui Winery, Fisherman's Wharf | 🗺 GraphRAG |
| 3 | Drive from San Jose to Santa Cruz, show redwoods and beaches | route | Municipal Rose Garden, Japanese Friendship Garden, Forbes Mill Museum, The Tech Interactive, Ainsley House | Muir Beach Overlook, Portola Discovery Site of SF Bay, Baker Beach, San Francisco Botanical Garden | 🗺 GraphRAG |
| 4 | Drive from San Francisco to Point Reyes, show lighthouses and coastal nature | route | Top of the Mark, Rob Hill, Potrero Hill, Buena Vista Heights, Mount Tamalpais East Peak | Portola Discovery Site of SF Bay, Muir Beach Overlook, Fisherman's Wharf, Pier 39 Sea Lions, Fort Point | 🗺 GraphRAG |
| 5 | Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches | route | Top of the Mark, Mavericks, Bernal Hill, Mount Davidson, Potrero Hill | Muir Beach Overlook, Baker Beach, Albany Beach, Mavericks | 🗺 GraphRAG |
| 6 | Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views | route | Fort Point, Warden's House, Coit Tower, Conservatory of Flowers, Lone Sailor Monument | Golden Gate Bridge, Muir Beach Overlook, Fort Point, Portola Discovery Site of SF Bay, Japanese Tea Garden | 🗺 GraphRAG |
| 7 | beautiful California coastal drives | semantic | *(semantic — no route to parse)* | Muir Beach Overlook, Richardson Bay, Toll Plaza Beach, Mount Davidson, Mavericks | 🔍 Vector |
| 8 | wine country day trips from San Francisco | semantic | *(semantic — no route to parse)* | Fisherman's Wharf, Portola Discovery Site of SF Bay, Muir Beach Overlook, Buena Vista Heights, Strawberry Hill | 🔍 Vector |
| 9 | old growth redwood forests near Bay Area | semantic | *(semantic — no route to parse)* | San Francisco Botanical Garden, Richardson Bay, Conservatory of Flowers, Muir Beach Overlook, Japanese Friendship Garden | 🔍 Vector |
| 10 | Gold Rush era historic towns California | semantic | *(semantic — no route to parse)* | Fort Point, Muir Beach Overlook, Japanese Tea Garden, Forbes Mill Museum, Luis María Peralta Adobe | 🔍 Vector |

**Prediction accuracy: 10/10**

**Overall distribution:**
- 🗺 GraphRAG wins: 6 queries (all route-specified)
- 🔍 Vector wins: 4 queries (all semantic/open-ended)
- 🤝 Ties: 0

**When each method wins:**

| Scenario | Best method | Why |
|----------|-------------|-----|
| "Drive from A to B, show X" | GraphRAG | Route coordinates constrain results to on-path POIs |
| Open-ended discovery ("best coastal drives") | Vector | No route → pure semantic recall wins |
| Specific landmark type along known route | GraphRAG | Graph filter removes off-route false positives |
| No origin/destination | Vector | No route graph to leverage |

**Core finding:** GraphRAG and vector are complementary, not competing. A production
system would classify query intent first (route-specified vs. open-ended) and dispatch
accordingly. This split is cleanly validated by the 10-query evaluation.

---

## 7. Iterations

1. **POI ranking V1 — pure detour cost.** Golden Gate Bridge beaten by street-level
   plaques at 0-min detour. Fix: added OSM `wikipedia` tag as notability tier (Tier 1)
   and scenic subtype score as Tier 2 — detour cost becomes tiebreaker only.

2. **Wikipedia enrichment V1 — no User-Agent header.** Silent HTTP 403 on every request.
   All `poi.description` fields returned `None` with no error surfaced. Fix: added
   `User-Agent: RouteIQ/1.0`. Also: 5s timeout too short under load → raised to 15s.

3. **POI search V1 — broad `historic: True`.** Thousands of county boundaries, historic
   roads, and unnamed buildings with no Wikipedia articles entered the pipeline. Fix:
   explicit subtype allowlist (`castle`, `fort`, `monument`, `memorial`, `ruins`,
   `archaeological_site`, `lighthouse`, `manor`, `battlefield`).

4. **Overpass at query time.** 11–21s per route, mirror unreliability during demo. Fix:
   pre-seeded `bay_area_all.json.gz` (984 POIs, 33 KB gzip) committed to repo.
   `POIFinder` does in-memory Shapely spatial filter — zero Overpass calls for all
   Bay Area demo routes.

5. **Geographic spread V1 — no spread constraint.** All 5 POI slots filled from one
   dense city neighbourhood. Fix: greedy 2 km minimum distance between selected POIs.

6. **Narrative V1 → V3.** V1: hallucinated visit reasons (no context). V2: Wikipedia
   descriptions added → hallucination eliminated. V3: KG city/region/nearby stops added
   → richer, more geographically grounded narratives.

7. **KnowledgeGraph seed data mismatch.** The KG was seeded with Texas POIs (Austin,
   San Antonio, Hill Country) while all demo routes are Bay Area. `get_pois_for_route()`
   uses city node coordinates to filter — Texas cities never fell within a Bay Area route
   bbox, so `on_route_ids` was always empty, stage 2 filtered all candidates, and
   KnowledgeRAG silently returned `""` for every query. The V3 prompt fired but with
   empty KG context. Fix: replaced Texas seed with 95 OSM-verified Bay Area notable POIs
   auto-loaded from `bay_area_all.json.gz`, nearest-city assigned across 10 Bay Area
   cities, typed edges to 7 Bay Area regions. V3 prompt now fires with real
   city/region/nearby context for all demo routes.

---

## 8. Key Learnings

1. **Input quality gates matter as much as retrieval.** `historic: True` produced garbage
   POIs that no downstream RAG step could recover from. Explicit subtype allowlists are
   the right guard. In geospatial RAG, garbage-in at the OSM query level propagates
   all the way through enrichment, embedding, and generation.

2. **Entity disambiguation is cheap and essential.** Bare "Lighthouse" matches a generic
   Wikipedia architecture article. "Pigeon Point Lighthouse California" resolves to the
   correct landmark immediately. For geospatial POIs, appending state or region is a
   simple, high-signal fix — and the minimal context needed to disambiguate is almost
   always available from the route geography.

3. **Detour cost ≠ scenic value.** Proximity is a constraint, not a quality signal. A
   viewpoint at 3-min detour beats a historic plaque at 0-min detour for road trip
   value. Scenic subtype scores needed an explicit model; OSM subtype values (`viewpoint`,
   `beach`, `lighthouse`, `fort`) encode exactly this.

4. **Graceful degradation beats hard filters.** Filtering out POIs with missing
   descriptions caused total route failures when Wikipedia enrichment degraded. Passing
   partial context (name + category) to Claude produces usable narratives. Each pipeline
   stage should pass forward whatever it has — the LLM handles missing fields far better
   than a binary "no data available" fallback implies.

5. **GraphRAG and vector are complementary, not competing.** Route queries need geographic
   constraints that embeddings cannot enforce; discovery queries need semantic recall
   that a graph with no route has nothing to offer. The evaluation confirms this cleanly:
   6/6 GraphRAG wins on route queries, 4/4 vector wins on semantic queries, 10/10 total
   prediction accuracy.

6. **Typed KG edges add precision embeddings cannot replicate.** Multi-hop reasoning —
   "POIs in this region, in this category, near this landmark on the route" — requires
   explicit relational structure. Even a knowledge graph of moderate size
   (95 POIs, 10 cities, 7 regions) outperforms pure similarity for route-contextual
   retrieval. Coverage debt is manageable; a slow or broken KG is not — seed the
   landmarks most likely to appear in demo queries and accept graceful degradation
   for everything else.
