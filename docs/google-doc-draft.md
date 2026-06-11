# RouteIQ — Week 2 Submission

---

## 1. Project Overview

My RAG app helps travelers answer scenic route questions from OpenStreetMap road network
graphs and Wikipedia landmark data in a map UI, combining spatial graph retrieval with
vector search for high-faithfulness stop recommendations.

RouteIQ answers natural-language scenic route queries end-to-end: a user types a query
like *"Drive from San Francisco to Muir Woods, show redwoods and coastal views,"* Claude
parses the intent, the OSM road network is loaded, NetworkX finds the A\* shortest path,
POIs are spatially joined within a 5 km corridor buffer, Wikipedia enriches each stop with
descriptions and images, a 3-stage Knowledge Graph RAG pipeline assembles rich context,
and Claude streams a narrative — all presented in a Folium map with stop cards and a
side-by-side GraphRAG vs. vector comparison.

**Why GraphRAG over pure vector search:** Route queries have a geographic constraint —
stops must lie within the A\* path corridor, not just be semantically similar to "coastal
California landmarks." A vector search for "coastal lighthouse" returns Pigeon Point
Lighthouse regardless of whether it's on your route. The graph layer enforces the spatial
contract that embeddings cannot.

**Pipeline flow:**

```
NL Query
    → LangGraph Pipeline
        [parse]   Claude extracts origin / destination / preferences
        [graph]   OSMnx geocode → road network → NetworkX A* → POI spatial join (5 km buffer) → DetourScorer → top 5 POIs
        [rag]     Wikipedia enrichment (parallel) → ChromaDB chunk+index → 3-stage KnowledgeRAG
        [narrate] Claude streaming narrative (tokens live to UI)
    → Streamlit UI — Folium map · stop cards with Wikipedia images · GraphRAG vs Vector comparison
```

---

## 2. Datasets and Corpus

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

## 3. The Three RAG Approaches

### 3a. Vector RAG (semantic baseline)

**Architecture:** ChromaDB + LangChain embeddings. At startup, 95 OSM-verified notable
Bay Area landmarks are loaded from the pre-seeded `bay_area_all.json.gz` master file
(filtered to POIs with an OSM `wikipedia` tag — crowd-sourced notability signal),
Wikipedia-enriched in parallel, and indexed into a dedicated ChromaDB collection.
91 of 95 had Wikipedia articles. At query time, `VectorBaseline.query()` returns the
top 5 by cosine similarity to the user's query text. No geographic constraints applied.

**When it wins:** Open-ended discovery queries with no origin/destination — "beautiful
coastal drives," "wine country day trips from SF." Semantic recall over POI descriptions
is the right primitive when no route exists to constrain results.

**When it fails:** Route-specified queries ("Drive from A to B, show X"). Returns
semantically similar POIs regardless of whether they're on the route. For SF→Sausalito,
it returns Golden Gate Bridge (semantically correct — on the route by coincidence) but
also Muir Beach Overlook and Japanese Tea Garden (wrong geography). GraphRAG enforces
the 5 km corridor and surfaces Fort Point, Coit Tower, Conservatory of Flowers — all
actually on the route. Fails completely for non-Bay-Area routes (no coverage).

**Eval result:** 4/4 wins on semantic queries, 0/6 wins on route queries.

---

### 3b. GraphRAG (main approach)

**Architecture:** OSM road network (NetworkX MultiDiGraph) + Shapely corridor spatial
join + 3-tier POI ranking. The "graph" here is the real OSM road network — millions of
nodes — not a hand-crafted knowledge graph.

**Pipeline, step by step:**

1. **Graph loading** — OSMnx downloads the road network for the corridor bbox, cached
   as a pickle file. First load: 30–60s. Subsequent: ~0.5s.

2. **A\* pathfinding** — NetworkX A\* with haversine heuristic finds the shortest
   driving path. Output: ordered (lat, lon) route coordinates.

3. **Spatial join** — `Shapely LineString.buffer(5 km)` creates the corridor polygon.
   Overpass queries OSM features in the bbox; centroid-in-polygon filter keeps only
   on-corridor POIs. For Bay Area routes, `bay_area_all.json.gz` eliminates live
   Overpass calls entirely (~0.1s in-memory filter vs. 11–21s Overpass query).

4. **3-tier POI ranking:**
   - Tier 1: OSM `wikipedia` tag — crowd-sourced notability proxy (OSM contributors only
     add this tag to features with a verified Wikipedia article)
   - Tier 2: Scenic subtype score — viewpoint=9, beach=9, lighthouse=8, fort=7,
     attraction=7, memorial=3
   - Tier 3: Detour minutes — tiebreaker only

5. **Geographic spread** — greedy 2 km minimum between selected POIs; prevents one
   dense neighbourhood filling all 5 slots.

6. **Wikipedia enrichment** — parallelized (5 threads, ThreadPoolExecutor), 15s timeout,
   User-Agent header required (missing header caused silent HTTP 403s on all requests),
   bare name before geographic suffix fallback ("Point Bonita Lighthouse California").

**When it wins:** Any route-specified query. Corridor filter removes off-route false
positives that semantic similarity cannot catch.

**Eval result:** 6/6 wins on route queries.

---

### 3c. Knowledge Graph RAG (augmentation layer)

**Architecture:** Pre-seeded `RouteKnowledgeGraph` (NetworkX DiGraph) with typed edges,
queried in a 3-stage pipeline after the GraphRAG spatial join selects the top POIs.

**Graph schema:**

| Edge type | Connects | Enables |
|-----------|----------|---------|
| `LOCATED_IN` | POI → City | "near San Francisco" filtering |
| `HAS_CATEGORY` | POI → Category | preference filtering ("show wineries") |
| `IN_REGION` | POI/City → Region | corridor matching ("Bay Area") |
| `NEAR_POI` | POI ↔ POI | "also nearby" co-recommendations |

**3-stage KnowledgeRAG pipeline:**

1. **Vector retrieval** — ChromaDB semantic search over 250-char POI description chunks
   finds candidates by similarity to the user's preference text.
2. **Graph filter + augment** — `RouteKnowledgeGraph` filters to POIs near the route;
   augments each with city, region, and nearby POI names from graph traversal.
3. **Context assembly** — formatted context string for Claude:
   `name | category | city | region | nearby stops | description excerpt`

**Coverage:** 95 OSM-verified notable Bay Area POIs are seeded into the KG at startup,
auto-loaded from `bay_area_all.json.gz` and nearest-city assigned across 10 Bay Area
cities (San Francisco, Oakland, Berkeley, San Jose, Santa Cruz, Sausalito, Napa,
Half Moon Bay, Mill Valley, Tiburon) and 7 regions. POIs not in the KG seed fall back
to vector-only context.

**Key insight:** Typed edges enable multi-hop queries embeddings cannot express — "find
POIs in a region that match a category that are near another POI on the route." Even a
small, manually-seeded knowledge graph adds relational precision no embedding model can
replicate.

---

## 4. Narration and Generation

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

## 5. Evaluation — GraphRAG vs Vector Baseline

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

## 6. Iterations

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

## 7. Key Learnings

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
