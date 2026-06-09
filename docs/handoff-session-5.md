# Session 5 Handoff — RouteIQ

## Start of next session
Say: `"continue from handoff, implement Day 4 UI and evaluation"`

---

## Current state

**Branch:** `feat/days-1-3-graph-rag-pipeline` — pushed  
**Tests:** 121/121 passing  
**Sessions complete:** Day 1 (graph), Day 2 (pipeline), Day 3 (RAG), Session 5 (knowledge graph layer)

---

## What was built this session (knowledge graph layer)

### New files
| File | What it does |
|---|---|
| `routeiq/graph/knowledge_graph_data.py` | Pure seed data: 15 POIs, 8 Cities, 5 Regions, 6 Categories, typed RELATIONSHIPS list |
| `routeiq/graph/knowledge_graph.py` | `RouteKnowledgeGraph` — NetworkX DiGraph, builds graph from seed data, NEAR_POI edges (≤25 km haversine), `enrich_poi(osm_id)`, `get_pois_for_route(route_coords)` |
| `routeiq/rag/poi_chunker.py` | `POIChunker` — RecursiveCharacterTextSplitter (chunk_size=250, overlap=20), indexes chunks as `{osm_id}_chunk_{i}`, `get_parent_osm_id()` static helper |
| `routeiq/rag/knowledge_rag.py` | `KnowledgeRAG` — 3-stage: Stage 1 vector search ChromaDB, Stage 2 graph filter (bbox) + augment (enrich_poi), Stage 3 context string |
| `tests/test_knowledge_graph.py` | 8 tests — node count, typed edges, enrich_poi, route filtering |
| `tests/test_poi_chunker.py` | 6 tests — splitting, chunk size, parent ID extraction, ChromaDB indexing |
| `tests/test_knowledge_rag.py` | 6 tests — stage 1/2/3 independently, empty collection, no route coords |

### Updated files
| File | Change |
|---|---|
| `routeiq/graph/__init__.py` | Added `RouteKnowledgeGraph` export |
| `routeiq/rag/__init__.py` | Added `POIChunker`, `KnowledgeRAG` exports |
| `routeiq/pipeline.py` | `_rag_node` — KnowledgeRAG 3-stage path + legacy fallback; new `poi_chunker` + `knowledge_rag` params |
| `routeiq/facade.py` | Auto-wires `RouteKnowledgeGraph`, `POIChunker(chunker_indexer)`, `KnowledgeRAG(chunker_indexer, kg)` |
| `routeiq/insights/prompts/narrative.py` | Added `NARRATIVE_PROMPT_V3` (name\|category\|city\|region\|nearby\|evidence format); `NARRATIVE_PROMPT = NARRATIVE_PROMPT_V3` |

### One bug found and fixed
`KnowledgeRAG._stage2_filter_augment` had a logic hole: when `route_coords` are provided but no city matches (empty `on_route_ids`), the original guard `if not is_on_route and on_route_ids` was falsy → all candidates passed through. Fixed by separating `no_route_specified = not route_coords` from the set emptiness check.

---

## What's next — Day 4

### 1. `day4_verify.py` — end-to-end smoke test (no UI needed)

Run the full pipeline with a real query and print the narrative + stop list. Confirms KnowledgeRAG is wired through to Claude. Does not need a browser.

```python
"""End-to-end smoke test for the KnowledgeRAG pipeline."""
import os
from langchain_anthropic import ChatAnthropic
from routeiq.facade import RouteIQFacade

llm = ChatAnthropic(model="claude-sonnet-4-6", api_key=os.environ["ANTHROPIC_API_KEY"])
facade = RouteIQFacade(llm)
result = facade.run("Drive from Austin to San Antonio, show me historic missions and natural springs")
print(result["narrative"])
```

### 2. Streamlit UI (recommended over FastAPI+React for speed)

File: `app.py`

```
pip install streamlit folium streamlit-folium
```

Key components:
- Text input for query
- `RouteIQFacade(llm).run(query)` on submit
- Folium map with route polyline + color-coded markers (category → color)
- Stop cards: name, detour time, why visit, Wikipedia thumbnail image

Marker color mapping:
```python
CATEGORY_COLORS = {
    "mission": "red",
    "historic": "orange",
    "natural": "green",
    "state_park": "darkgreen",
    "winery": "purple",
    "tourism": "blue",
}
```

### 3. 10-query GraphRAG vs vector-only baseline evaluation

`VectorBaseline` is already implemented in `routeiq/rag/vector_baseline.py`.

For each of the 10 queries:
1. Run `RouteIQFacade.run(query)` → GraphRAG result
2. Run `VectorBaseline(indexer).query(query_text)` → vector-only result
3. Score: did GraphRAG surface more spatially-relevant stops? Did it have region context the vector-only result lacked?

Create `evaluation/eval_10_queries.py` — prints a table of results.

### 4. Day 5 demo queries (4 canned routes, already in CLAUDE.md)
- Austin → San Antonio (historic missions, natural springs)
- Austin → Fredericksburg → San Antonio (Hill Country: wineries, Enchanted Rock, Luckenbach)
- San Antonio → Marble Falls (Highland Lakes, swimming holes)
- Houston → Austin (bluebonnet trail, Round Top)

### 5. Nebius (after credentials arrive)
Swap embedding model in `routeiq/rag/poi_indexer.py` (the `routeiq_chunks` collection used by KnowledgeRAG):

```python
# In RouteIQFacade.__init__, replace:
_chunker_indexer = POIIndexer(collection_name="routeiq_chunks")
# With:
from langchain_community.embeddings import NebiusEmbeddings
_nebius_embed = NebiusEmbeddings(model="BAAI/bge-en-icl", api_key=os.environ["NEBIUS_API_KEY"])
_chunker_indexer = POIIndexer(collection_name="routeiq_chunks", embedding_function=_nebius_embed)
```

Note: `POIIndexer.__init__` will need an `embedding_function` param added and passed to `get_or_create_collection`.

---

## Architecture summary (full system as of end of session 5)

```
NL Query
  → RoutePipeline (LangGraph)
      [parse]   QueryParser (Claude)          → origin, destination, preferences
      [graph]   GraphLoader + RouteGraph       → RouteResult (coords, length_km, drive_time_min)
                POIFinder → DetourScorer → POISelector → top_pois
      [rag]     WikipediaFetcher              → enriches POI.description + image_url
                POIChunker                   → chunks descriptions → ChromaDB "routeiq_chunks"
                KnowledgeRAG                 → 3-stage GraphRAG:
                  Stage 1: ChromaDB vector search (preferences → ranked chunks)
                  Stage 2: RouteKnowledgeGraph filter (bbox) + augment (city/region/nearby)
                  Stage 3: context string → NarrativeChain
      [narrate] NarrativeChain (Claude V3)    → narrative text
  → UI (app.py)                              → Folium map + stop cards
```

---

## Key gotchas

| Gotcha | Detail |
|---|---|
| Two ChromaDB collections | `routeiq_pois` (full descriptions, POIIndexer legacy) vs `routeiq_chunks` (chunk text, used by KnowledgeRAG) |
| ChromaDB shared state in tests | Always uuid-suffix collection names in test helpers |
| OSMnx 2.x bbox | `(west, south, east, north)` — not `(north, south, east, west)` |
| nearest_nodes | `X=lon, Y=lat` |
| Shapely LineString | `(lon, lat)` |
| KG POI ids | `kg_` prefix; OSM POIs use numeric OSM ids |
| Stage 2 filter bug (fixed) | `no_route_specified = not route_coords` must be separate from `on_route_ids` emptiness |

---

## What stays the same

- Road network graph, A*, DetourScorer, POISelector — untouched
- WikipediaFetcher — untouched  
- All 121 existing tests — must stay green
- LangGraph pipeline structure — only `_rag_node` body changed
