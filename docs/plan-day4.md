# Day 4 — Knowledge Graph Layer + 3-Stage GraphRAG Pipeline

## Goal
Add a knowledge graph (POI/City/Region/Category nodes with typed relationships) to make
RouteIQ match the course demo's GraphRAG pattern. Implement the 3-stage pipeline:
vector search → graph filter+augment → LLM synthesis. Build the Streamlit UI with map
and stop cards. Run the 10-query GraphRAG vs. vector-only evaluation.

---

## Why this layer is needed

The course demo (Project 3) uses:
1. **Vector search** over Chunk nodes → find semantically similar candidates
2. **Graph traversal** → filter by typed relationship (WORKED_AT), augment with HAS_SKILL
3. **LLM synthesis** → enriched context → recommendation

RouteIQ Days 1-3 have the road network graph (navigation) and vector search (ChromaDB),
but NOT a knowledge graph with typed entity relationships. This day fills that gap.

**Our equivalent mapping:**
| Course demo | RouteIQ Day 4 |
|-------------|--------------|
| Candidate nodes | POI nodes |
| Company nodes | City nodes |
| Role/Skill nodes | Region/Category nodes |
| `WORKED_AT` company filter | `LOCATED_IN` city that is `ON_ROUTE` filter |
| `HAS_SKILL` traversal | `HAS_CATEGORY`, `IN_REGION`, `NEAR_POI` traversal |
| Chunk -[PART_OF]→ Candidate | Chunk -[chunk_of]→ POI (via chunk id prefix) |

---

## Files to create

```
routeiq/graph/
  knowledge_graph_data.py    seed data: 15 POIs, 8 Cities, 5 Regions, 6 Categories (34+ nodes)
  knowledge_graph.py         RouteKnowledgeGraph (Registry + NetworkX DiGraph)

routeiq/rag/
  poi_chunker.py             POIChunker (RecursiveCharacterTextSplitter, chunk_size=250)
  knowledge_rag.py           KnowledgeRAG (3-stage pipeline)

routeiq/insights/prompts/
  narrative.py               add NARRATIVE_PROMPT_V3 (region + nearby POIs in context)

day4_verify.py

tests/
  test_knowledge_graph.py    (8 tests)
  test_poi_chunker.py        (6 tests)
  test_knowledge_rag.py      (6 tests)
```

## Files to update

```
routeiq/graph/__init__.py          add RouteKnowledgeGraph export
routeiq/rag/__init__.py            add POIChunker, KnowledgeRAG exports
routeiq/pipeline.py                _rag_node uses KnowledgeRAG 3-stage
routeiq/facade.py                  wire RouteKnowledgeGraph + POIChunker + KnowledgeRAG
```

---

## Implementation order

```
1. knowledge_graph_data.py     pure data, no logic
2. knowledge_graph.py          NetworkX graph, test immediately
3. tests/test_knowledge_graph.py
4. poi_chunker.py              text splitter + ChromaDB
5. tests/test_poi_chunker.py
6. knowledge_rag.py            3-stage pipeline
7. tests/test_knowledge_rag.py
8. __init__.py updates
9. pipeline.py _rag_node update
10. facade.py wiring
11. NARRATIVE_PROMPT_V3
12. day4_verify.py
13. Full test suite (target 120+ tests)
14. Nebius swap (after credentials)
```

---

## Step 1 — knowledge_graph_data.py (seed data)

### Node counts (satisfies 20-node submission requirement)
- 15 POI nodes
- 8 City nodes
- 5 Region nodes
- 6 Category nodes
- **Total: 34 nodes**

### POI seed data (15 POIs)
```python
POIS = [
  {osm_id:"kg_alamo",        name:"The Alamo",                    category:"mission",    city:"San Antonio",   region:"San Antonio Missions",  lat:29.4260, lon:-98.4861, wikipedia_tag:"en:The Alamo"},
  {osm_id:"kg_concepcion",   name:"Mission Concepción",           category:"mission",    city:"San Antonio",   region:"San Antonio Missions",  lat:29.4063, lon:-98.4874, wikipedia_tag:"en:Mission Concepción"},
  {osm_id:"kg_sanjuan",      name:"Mission San Juan",             category:"mission",    city:"San Antonio",   region:"San Antonio Missions",  lat:29.3630, lon:-98.4815, wikipedia_tag:"en:Mission San Juan Capistrano (Texas)"},
  {osm_id:"kg_national_museum", name:"San Antonio Missions NHP", category:"historic",   city:"San Antonio",   region:"San Antonio Missions",  lat:29.3596, lon:-98.4760, wikipedia_tag:"en:San Antonio Missions National Historical Park"},
  {osm_id:"kg_natural_bridge",  name:"Natural Bridge Caverns",   category:"tourism",    city:"New Braunfels", region:"Hill Country",          lat:29.6927, lon:-98.3419, wikipedia_tag:"en:Natural Bridge Caverns"},
  {osm_id:"kg_gruene",       name:"Gruene Historic District",     category:"historic",   city:"New Braunfels", region:"Blanco Valley",         lat:29.7380, lon:-98.1096, wikipedia_tag:"en:Gruene, Texas"},
  {osm_id:"kg_guadalupe",    name:"Guadalupe River State Park",   category:"state_park", city:"New Braunfels", region:"Hill Country",          lat:29.8472, lon:-98.4896, wikipedia_tag:"en:Guadalupe River State Park"},
  {osm_id:"kg_canyon_lake",  name:"Canyon Lake",                  category:"natural",    city:"New Braunfels", region:"Highland Lakes",        lat:29.8716, lon:-98.2617, wikipedia_tag:"en:Canyon Lake (Texas)"},
  {osm_id:"kg_enchanted_rock", name:"Enchanted Rock",             category:"natural",    city:"Fredericksburg",region:"Hill Country",          lat:30.5063, lon:-98.8198, wikipedia_tag:"en:Enchanted Rock"},
  {osm_id:"kg_luckenbach",   name:"Luckenbach Texas",             category:"tourism",    city:"Fredericksburg",region:"Texas Wine Country",    lat:30.1849, lon:-98.7384, wikipedia_tag:"en:Luckenbach, Texas"},
  {osm_id:"kg_old_tunnel",   name:"Old Tunnel State Park",        category:"natural",    city:"Fredericksburg",region:"Texas Wine Country",    lat:30.1716, lon:-98.7505, wikipedia_tag:"en:Old Tunnel State Park"},
  {osm_id:"kg_becker",       name:"Becker Vineyards",             category:"winery",     city:"Fredericksburg",region:"Texas Wine Country",    lat:30.2208, lon:-98.8661, wikipedia_tag:"en:Becker Vineyards"},
  {osm_id:"kg_pedernales",   name:"Pedernales Falls State Park",  category:"state_park", city:"Marble Falls",  region:"Hill Country",          lat:30.3077, lon:-98.2566, wikipedia_tag:"en:Pedernales Falls State Park"},
  {osm_id:"kg_hamilton",     name:"Hamilton Pool Preserve",       category:"natural",    city:"Austin",        region:"Hill Country",          lat:30.3427, lon:-98.1269, wikipedia_tag:"en:Hamilton Pool Preserve"},
  {osm_id:"kg_wimberley",    name:"Wimberley",                    category:"tourism",    city:"San Marcos",    region:"Blanco Valley",         lat:29.9977, lon:-98.0986, wikipedia_tag:"en:Wimberley, Texas"},
]
```

### Typed relationships
```python
RELATIONSHIPS = (
    # POI -[LOCATED_IN]→ City  (15 edges)
    [("kg_alamo", "LOCATED_IN", "San Antonio"), ...]

    # POI -[HAS_CATEGORY]→ Category  (15 edges, auto-generated from POIS)
    + [(p["osm_id"], "HAS_CATEGORY", p["category"]) for p in POIS]

    # City -[IN_REGION]→ Region  (7 edges)
    + [("San Antonio", "IN_REGION", "San Antonio Missions"), ...]
)
```

---

## Step 2 — knowledge_graph.py (RouteKnowledgeGraph)

**Design:**
- NetworkX DiGraph (not Neo4j — same graph algorithms, no server overhead)
- Node attributes: `type` field distinguishes POI/City/Region/Category
- NEAR_POI edges: auto-generated for all POI pairs within 25km (haversine)

**Public API:**
```python
class RouteKnowledgeGraph:
    def __init__(self)             # calls _build() automatically
    def enrich_poi(osm_id) → dict  # {city, region, category, nearby_pois: [names]}
    def get_pois_for_route(route_coords) → list[str]  # osm_ids in route bounding box
    def get_all_pois() → list[str]
    def node_count() → int
```

**`get_pois_for_route` logic:**
```python
# 1. Compute route bounding box from route_coords + 0.3 deg padding
# 2. Find all City nodes within that bbox
# 3. Return osm_ids of POI nodes LOCATED_IN those cities
```

**`enrich_poi` logic:**
```python
# Traverse outgoing edges from osm_id:
# → LOCATED_IN edge → city name
# → city → IN_REGION edge → region name
# → HAS_CATEGORY edge → category name
# → NEAR_POI edges → list of neighbor POI names
```

**`_add_near_poi_edges` — auto-generated proximity edges:**
```python
# For every pair of POI nodes, compute haversine distance
# If dist <= 25km → add bidirectional NEAR_POI edge with dist_km attribute
```

---

## Step 3 — poi_chunker.py (POIChunker)

**Design mirrors course demo exactly:**
- `RecursiveCharacterTextSplitter(chunk_size=250, chunk_overlap=20)` — same params as demo
- Each chunk becomes a synthetic POI for POIIndexer storage
- Chunk ID format: `"{osm_id}_chunk_{i}"` — parent recoverable via string split
- Mirrors: `Chunk -[PART_OF]→ Candidate` from course demo

```python
class POIChunker:
    def chunk_and_index(self, pois: list[POI]) -> int:
        for poi in pois:
            chunks = self._splitter.split_text(poi.description)
            for i, text in enumerate(chunks):
                chunk_poi = POI(..., osm_id=f"{poi.osm_id}_chunk_{i}", description=text)
            self._indexer.index(chunk_pois)

    @staticmethod
    def get_parent_osm_id(chunk_id: str) -> str:
        return chunk_id.rsplit("_chunk_", 1)[0]
```

**Important:** Use a SEPARATE ChromaDB collection `"routeiq_chunks"` for chunks,
distinct from `"routeiq_pois"` (full descriptions). They serve different retrieval patterns.

---

## Step 4 — knowledge_rag.py (KnowledgeRAG — 3-stage pipeline)

### Stage 1 — Vector Search
```python
def _stage1_vector_search(self, preferences, n):
    # Embed preferences text → query ChromaDB chunks collection
    query_text = " ".join(preferences) or "scenic landmark"
    results = self._collection.query(query_texts=[query_text], n_results=k, ...)

    # De-duplicate: multiple chunks from same POI → keep highest score
    seen_pois: dict[str, dict] = {}
    for chunk_id, doc, meta, dist in zip(...):
        parent_id = POIChunker.get_parent_osm_id(chunk_id)
        score = 1.0 - dist
        if parent_id not in seen_pois or seen_pois[parent_id]["score"] < score:
            seen_pois[parent_id] = {osm_id, name, score, evidence=doc}

    return sorted(seen_pois.values(), key=lambda x: x["score"], reverse=True)
```

### Stage 2 — Graph Filter + Augment
```python
def _stage2_filter_augment(self, candidates, route_coords):
    on_route_ids = set(self._kg.get_pois_for_route(route_coords))
    enriched = []
    for candidate in candidates:
        if candidate["osm_id"] not in on_route_ids and on_route_ids:
            continue    # filtered out — city not on route
        graph_data = self._kg.enrich_poi(candidate["osm_id"])
        enriched.append({**candidate, **graph_data})
    return enriched
```

### Stage 3 — Build Context
```python
def _stage3_build_context(self, enriched):
    lines = []
    for item in enriched:
        nearby = ", ".join(item.get("nearby_pois", [])[:3]) or "none"
        lines.append(
            f"{item['name']} | {item.get('category')} | "
            f"{item.get('city')} | {item.get('region')} | "
            f"nearby: {nearby} | {item['evidence']}"
        )
    return "\n\n".join(lines)
```

---

## Step 5 — NARRATIVE_PROMPT_V3

```
Each stop is formatted as:
  name | category | city | region | nearby stops | description excerpt

Instructions:
- Write engaging opening narrative (3-5 sentences) capturing the route's character and region.
- List each stop: name | detour time | one sentence why to visit, drawn from description.
- Mention the region where it adds flavour (e.g. "deep in the Hill Country").
- Ground every fact in provided context. Do not invent locations or distances.
```

---

## Step 6 — Update `_rag_node` in pipeline.py

```python
def _rag_node(self, state):
    if not state.get("top_pois"):
        return {"error": "no_pois_found", ...}

    top_pois = state["top_pois"]

    # Wikipedia enrichment (always — needed for KnowledgeRAG Stage 1)
    if self._wikipedia_fetcher:
        for sp in top_pois:
            self._wikipedia_fetcher.enrich(sp.poi)

    if self._knowledge_rag:
        # Chunk + index for vector search (Stage 1)
        if self._poi_chunker:
            self._poi_chunker.chunk_and_index([sp.poi for sp in top_pois])

        # Run 3-stage KnowledgeRAG pipeline
        poi_context = self._knowledge_rag.query(
            preferences=state.get("preferences") or [],
            route_coords=state["route_result"].route_coords,
        )
    else:
        # Fallback: plain Day 3 context format
        poi_context = self._build_poi_context(top_pois)

    return {"poi_context": poi_context}
```

Add to `RoutePipeline.__init__` params: `knowledge_rag=None`, `poi_chunker=None`.

---

## Step 7 — Update facade.py

```python
from routeiq.graph import ..., RouteKnowledgeGraph
from routeiq.rag import ..., POIChunker, KnowledgeRAG

# In __init__:
_kg = RouteKnowledgeGraph()
_chunk_indexer = POIIndexer(collection_name="routeiq_chunks")
RoutePipeline(
    ...,
    wikipedia_fetcher=WikipediaFetcher(),
    poi_indexer=_chunk_indexer,
    poi_retriever=POIRetriever(_chunk_indexer),
    poi_chunker=POIChunker(_chunk_indexer),
    knowledge_rag=KnowledgeRAG(_chunk_indexer, _kg),
)
```

---

## Step 8 — Tests

### `tests/test_knowledge_graph.py` (8 tests)
```
test_node_count_exceeds_20          → node_count() >= 34
test_poi_has_located_in_city        → Alamo → San Antonio edge exists
test_poi_has_category               → HAS_CATEGORY edge exists
test_city_has_in_region             → San Antonio → San Antonio Missions edge
test_near_poi_edges_created         → Alamo and Mission Concepción are NEAR_POI (< 25km)
test_enrich_poi_returns_all_fields  → city, region, category, nearby_pois all present
test_get_pois_for_route_austin_sa   → SA missions returned for Austin→SA bbox
test_empty_coords_returns_empty     → get_pois_for_route([]) → []
```

### `tests/test_poi_chunker.py` (6 tests)
```
test_long_description_splits        → 500-char text produces 2+ chunks
test_chunk_size_respected           → all chunks <= 250 chars
test_poi_without_description_skipped
test_chunk_id_contains_parent_osm_id
test_get_parent_osm_id_extracts     → "kg_alamo_chunk_2" → "kg_alamo"
test_indexes_chunks_to_chromadb     → collection.count() > 0 after chunk_and_index
```

### `tests/test_knowledge_rag.py` (6 tests)
```
test_stage1_returns_ranked_by_score (mock ChromaDB)
test_stage1_deduplicates_same_poi_chunks
test_stage2_filters_offroute_pois
test_stage2_augments_with_graph_data → city, region in result
test_stage3_context_contains_region
test_empty_collection_returns_empty_string
```

---

## Step 9 — Nebius swap (after credentials arrive)

In `routeiq/rag/poi_chunker.py` or the collection creation:
```python
# Replace ChromaDB default local embeddings with Nebius model
from langchain_chroma import Chroma
from langchain_community.embeddings import NebiusEmbeddings

nebius_embeddings = NebiusEmbeddings(
    model="BAAI/bge-en-icl",
    api_key=os.environ["NEBIUS_API_KEY"],
)
# Use Chroma LangChain wrapper instead of raw chromadb client
vectorstore = Chroma(
    collection_name="routeiq_chunks",
    embedding_function=nebius_embeddings,
    persist_directory="./cache/chroma",
)
```
This satisfies the submission requirement: at least one model call through Nebius.

---

## Step 10 — day4_verify.py

```
Step 1: Build RouteKnowledgeGraph — print node count, sample enrich_poi result
Step 2: POIChunker — chunk 3 sample POIs, print chunk count + first chunk
Step 3: KnowledgeRAG Stage 1 — vector search for "historic missions"
Step 4: KnowledgeRAG Stage 2 — graph filter for Austin→SA route_coords
Step 5: KnowledgeRAG Stage 3 — print final context string
Step 6: Full pipeline run via RouteIQFacade (stub LLM if no API key)
```

---

## 10-query GraphRAG vs. Vector Baseline evaluation (Day 4)

Run these 10 queries through both `RouteIQFacade` (GraphRAG) and `VectorBaseline`:

| # | Query | Expected winner |
|---|-------|----------------|
| 1 | Austin to SA, historic missions | GraphRAG (spatial + entity) |
| 2 | Austin to SA, natural swimming holes | GraphRAG |
| 3 | Austin to Fredericksburg, wineries | GraphRAG |
| 4 | Austin to SA, Hill Country | GraphRAG (region traversal) |
| 5 | San Antonio to Marble Falls, lakes | GraphRAG |
| 6 | What are interesting historic places in Texas? | Vector (no route) |
| 7 | Show me natural landmarks | Vector (no route constraint) |
| 8 | Austin to SA, show me everything | GraphRAG (graph limits scope) |
| 9 | Houston to Austin, scenic stops | GraphRAG |
| 10 | Texas wine country experiences | Vector (no route; semantic wins) |

Document: what each approach returned, which was more accurate, why.

---

## Key gotchas

| Gotcha | Detail |
|--------|--------|
| `routeiq_chunks` vs `routeiq_pois` | Use separate ChromaDB collections — chunks (250-char) for Stage 1 vector search, full descriptions (500-char) for retrieval display |
| UUID collection names in tests | Same rule as Day 3 — EphemeralClient shares state |
| `_rag_node` preferences source | `state.get("preferences")` — already in PipelineState from parse node |
| `route_coords` source | `state["route_result"].route_coords` — set in graph node |
| KnowledgeRAG with no route_coords | `get_pois_for_route([])` returns all POIs — acceptable fallback |
| enrich_poi region traversal | Must go POI → LOCATED_IN → City → IN_REGION → Region (two hops) |
| NEAR_POI is bidirectional | `_add_near_poi_edges` adds A→B AND B→A with same dist_km |

---

## Verification

```bash
python3 -m pytest tests/ -v      # target: 120+ tests (all passing)
python3 day4_verify.py           # requires network + ANTHROPIC_API_KEY for full run
```
