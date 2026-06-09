# RouteIQ — Master Implementation Plan

Scenic route intelligence: NL query → Graph RAG → Wikipedia enrichment → Claude narrative.

---

## Project one-liner (submission doc)

> My RAG app helps travelers answer scenic route questions from OpenStreetMap road network
> graphs and Wikipedia landmark data in a map UI, combining spatial graph retrieval with
> vector search for high-faithfulness stop recommendations.

---

## Architecture

```
NL Query
    ↓
[parse]    QueryParser (Claude)          extract origin, destination, preferences
    ↓
[graph]    Road Network Layer            A* path → spatial buffer → candidate POIs
             OSMnx road graph            50k+ nodes, disk-cached, Austin→SA corridor
             RouteGraph (A*)             haversine heuristic, NetworkX MultiDiGraph
             POIFinder (Shapely)         5km buffer, tourism/historic/natural features
             DetourScorer                haversine round-trip cost per POI
             POISelector                 top-5, category filter, detour sort
    ↓
[rag]      RAG Layer (3-stage)
             Stage 1 — Vector Search     embed preferences → ChromaDB chunks → candidates
             Stage 2 — Graph Filter      knowledge graph: ON_ROUTE filter + entity traversal
             Stage 3 — Context Build     name | category | city | region | nearby | description
             WikipediaFetcher            REST API → description + thumbnail per POI
             POIChunker                  RecursiveTextSplitter (250 chars) → ChromaDB
             KnowledgeRAG                orchestrates 3 stages
    ↓
[narrate]  NarrativeChain (Claude)       route + enriched POI context → narrative + stop list
    ↓
[edge]     Conditional edges             fallback on: unparseable / geocode fail /
                                         route not found / too long / no POIs
    ↓
UI         Streamlit + Folium            map + POI markers + stop cards with Wikipedia images
```

---

## Day-by-day plan reference

| Day | What | Detail doc | Status |
|-----|------|-----------|--------|
| **Day 1** | Graph foundation | [plan-day1 (Graph-Foundation-Implementation.md)](Graph-Foundation-Implementation.md) | ✅ DONE — 21 tests |
| **Day 2** | Routing + pipeline | [plan-day2.md](plan-day2.md) | ✅ DONE — 73 tests |
| **Day 3** | RAG layer | [plan-day3.md](plan-day3.md) | ✅ DONE — 101 tests |
| **Day 4** | Knowledge graph + UI + eval | [plan-day4.md](plan-day4.md) | 🔲 NEXT |
| **Day 5** | Demo prep + submission | [plan-day5.md](plan-day5.md) | 🔲 TODO |

---

## Technology stack

| Component | Tool | Notes |
|-----------|------|-------|
| Road network | OSMnx >= 2.0 | bbox=(west,south,east,north) — pin to 2.x API |
| Graph traversal | NetworkX | A* + haversine heuristic, MultiDiGraph |
| Knowledge graph | NetworkX DiGraph | POI/City/Region/Category nodes, typed edges |
| Pipeline | LangGraph | Named nodes + conditional edges + TypedDict state |
| Chains | LangChain (LCEL) | prompt \| llm \| StrOutputParser() |
| LLM | Claude Sonnet 4.6 | via ChatAnthropic (langchain-anthropic) |
| Embeddings | ChromaDB default → Nebius | Swap to Nebius for submission requirement |
| Vector store | ChromaDB | Local PersistentClient, collection_name param |
| Wikipedia | REST API | /api/rest_v1/page/summary/{title} |
| Text splitting | LangChain RecursiveCharacterTextSplitter | chunk_size=250, overlap=20 |
| Map rendering | Folium | Standalone HTML, Streamlit-embedded |
| UI | Streamlit | streamlit-folium for map |

---

## File map (complete)

```
routeiq/
  graph/
    route_result.py          RouteResult dataclass
    poi.py                   POI dataclass (name, category, lat, lon, osm_id,
                               wikipedia_tag, image_url, description)
    graph_loader.py          GraphLoader — OSMnx load + disk cache (Registry)
    route_graph.py           RouteGraph — A* pathfinding (Strategy)
    poi_finder.py            POIFinder — Shapely buffer spatial join (Pipeline)
    knowledge_graph_data.py  seed data: 34+ nodes (Day 4)
    knowledge_graph.py       RouteKnowledgeGraph — NetworkX DiGraph (Day 4)
    __init__.py

  routing/
    scored_poi.py            ScoredPOI dataclass
    detour_scorer.py         DetourScorer — haversine round-trip (Strategy)
    poi_selector.py          POISelector — top-N + category filter (Strategy)
    __init__.py

  rag/
    wikipedia_fetcher.py     WikipediaFetcher — description + thumbnail (Strategy)
    poi_indexer.py           POIIndexer — ChromaDB upsert (Registry)
    poi_retriever.py         POIRetriever — get_context by id (Facade)
    vector_baseline.py       VectorBaseline — semantic-only query (Strategy)
    poi_chunker.py           POIChunker — chunk + index (Pipeline) (Day 4)
    knowledge_rag.py         KnowledgeRAG — 3-stage pipeline (Day 4)
    __init__.py

  insights/
    query_parser.py          QueryParser — NL → JSON intent (Chain)
    narrative_chain.py       NarrativeChain — route + POIs → narrative (Chain)
    fallback_chain.py        FallbackChain — error → user message (Chain)
    prompts/
      system.py              SYSTEM_PROMPT
      query_parser.py        QUERY_PARSER_PROMPT (V1 active)
      narrative.py           NARRATIVE_PROMPT (V1→V2→V3)
      fallback.py            FALLBACK_PROMPT
      __init__.py
    examples/
      query_parser_examples.py   FEW_SHOT_EXAMPLES
      __init__.py
    __init__.py

  pipeline.py                RoutePipeline — LangGraph state machine
  facade.py                  RouteIQFacade — DI entry point (Facade)
  __init__.py

app.py / main.py             Streamlit entry point (Day 4)

tests/
  test_graph_loader.py       (7 tests)
  test_route_graph.py        (7 tests)
  test_poi_finder.py         (7 tests)
  test_detour_scorer.py      (9 tests)
  test_poi_selector.py       (8 tests)
  test_query_parser.py       (8 tests)
  test_narrative_chain.py    (6 tests)
  test_fallback_chain.py     (3 tests)
  test_pipeline.py           (17 tests)
  test_wikipedia_fetcher.py  (11 tests)
  test_poi_indexer.py        (8 tests)
  test_poi_retriever.py      (4 tests)
  test_vector_baseline.py    (5 tests)
  test_knowledge_graph.py    (8 tests)  Day 4
  test_poi_chunker.py        (6 tests)  Day 4
  test_knowledge_rag.py      (6 tests)  Day 4

day1_verify.py               graph + map
day2_verify.py               pipeline (stub LLM fallback)
day3_verify.py               Wikipedia + ChromaDB + vector baseline
day4_verify.py               3-stage KnowledgeRAG end-to-end

docs/
  plan-master.md             this file
  plan-day2.md
  plan-day3.md
  plan-day4.md
  Graph-Foundation-Implementation.md   (Day 1 detailed plan)
  Architecture-and-Design-Decisions.md
  handoff-session-2.md
  handoff-session-4.md       knowledge graph implementation plan + code stubs
```

---

## Design patterns used

| Pattern | Where |
|---------|-------|
| Facade | RouteIQFacade — single entry point |
| Strategy | DetourScorer, POISelector, WikipediaFetcher, VectorBaseline, KnowledgeRAG |
| Pipeline | POIFinder, POIChunker, RoutePipeline (LangGraph) |
| Registry | GraphLoader (disk cache), POIIndexer (ChromaDB), RouteKnowledgeGraph |
| Chain | QueryParser, NarrativeChain, FallbackChain (LangChain LCEL) |
| Dependency Injection | LLM + all components injected via Facade constructor |

---

## Critical gotchas (never forget)

| Gotcha | Detail |
|--------|--------|
| OSMnx 2.x bbox order | `(west, south, east, north)` — NOT (north, south, east, west) |
| nearest_nodes arg order | `ox.distance.nearest_nodes(G, X=lon, Y=lat)` — X=longitude |
| Shapely coord order | `LineString([(lon, lat)])` — Shapely uses (x=lon, y=lat) |
| ChromaDB test isolation | `EphemeralClient()` shared in-process → always uuid-suffix collection name |
| cosine similarity | ChromaDB returns *distance* → `similarity = 1.0 - distance` |
| `_parse_error` vs exception | QueryParser never raises — returns dict with `_parse_error` key |
| poi_context None vs "" | `if poi_context is not None` — empty string is valid, None means "use fallback format" |
| Patch paths in tests | `"osmnx.geocode"` and `"routeiq.pipeline.RouteGraph"` |
| NEAR_POI is bidirectional | Add both A→B and B→A edges in knowledge graph |

---

## Submission checklist

| Deliverable | Status |
|-------------|--------|
| GitHub repo (clean code, requirements.txt, README) | 🔲 README needed |
| Demo recording ≤ 5 min | 🔲 Day 5 |
| Google Doc (overview, datasets, prompts, iterations, learnings) | 🔲 Day 5 |
| 10-query GraphRAG vs vector comparison | 🔲 Day 4 |
| Nebius for at least one model call | 🔲 After credentials |
| 4 canned demo queries working end-to-end | 🔲 Day 5 |

---

## 4 canned demo queries (Day 5)

```
1. "Drive from Austin to San Antonio, show me historic towns and natural springs"
2. "Austin to Fredericksburg to San Antonio, Hill Country wineries and Enchanted Rock"
3. "San Antonio to Marble Falls, Highland Lakes and swimming holes"
4. "Houston to Austin, bluebonnet trail and Round Top"
```

Each should show: route map + stop cards with real Wikipedia images + narrative.
