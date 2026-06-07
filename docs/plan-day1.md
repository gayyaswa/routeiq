# Day 1 Planning — RouteIQ Architecture

## What we decided and why

### Graph RAG over plain RAG
Plain RAG retrieves by semantic similarity. It has no concept of "along a route."
A query like "scenic stops between Austin and San Antonio" requires knowing which landmarks
are spatially adjacent to the route — that's a graph problem, not a similarity problem.

Decision: road network is the graph, pathfinding is the retriever, LLM narrates the result.
The graph does spatial reasoning; the LLM does language. Clean separation.

### NetworkX over Neo4j (for Week 1)
Neo4j requires a running server, schema setup, and Cypher queries.
NetworkX loads directly from OSMnx, stays in memory, and supports A*/shortest_path natively.
The graph algorithms are identical — the infra overhead is not worth it for a one-week MVP.

Decision: NetworkX for Week 1. Revisit Neo4j when multi-city persistence or graph size
exceeds memory.

### OSMnx as the data source
Free, global, rich attributes (road class, speed, POI tags, Wikipedia links).
No API key required. Load any region by city name or bounding box.
POI layer includes tourism, historic, natural features with wikipedia tag for RAG grounding.

Decision: OSMnx is the right call. No synthetic data, no paid APIs, works offline.

### ChromaDB over Pinecone/Weaviate
Local, no server, LangChain native integration.
For Week 1, retrieval is mostly by POI ID (graph pre-filters spatially, RAG just fetches
the document). Semantic search is only used for intent extraction from the NL query.
A cloud vector DB adds infra complexity for no Week 1 benefit.

Decision: ChromaDB local. Swap to Pinecone/Weaviate when multi-user or cloud deployment needed.

### Two-layer retrieval (Graph RAG + RAG)
Graph RAG: find which POIs are actually on the route → spatial truth
RAG: fetch rich descriptions for those POIs → language grounding
LLM: synthesize into narrative → user-facing answer

The key insight: RAG alone would hallucinate "nearby" without spatial truth.
Graph alone would return dry node IDs without language. Both layers are necessary.

### Tech stack not locked to Streamlit
The Portfolio app's Streamlit conventions were project-specific, not universal.
RouteIQ UI is TBD — could be Streamlit (fast), FastAPI+React (richer map interaction),
or CLI demo for Week 1. Decision deferred to Day 4 once core logic is working.

## Options considered and rejected

**LangGraph for the pipeline:** Adds orchestration overhead. The pipeline is linear
(query → graph → RAG → response) — a simple Pipeline class is clearer and easier to debug.
Revisit LangGraph if the pipeline branches or needs retry logic.

**Real-time traffic data (Waze, 511.org):** Out of scope Week 1. Static OSM is enough
to prove the Graph RAG concept. Real-time adds polling complexity and API rate limits.

**Fine-tuning Week 1:** No training data yet. Fine-tuning requires (query, context, answer)
pairs generated from the running system. Build the system first, generate data, fine-tune later.

## What we'll know after Day 1

Whether OSMnx can load a corridor (Austin → San Antonio) fast enough for interactive use,
and whether the spatial join finds meaningful POIs along that route. If the graph load is
slow (>30s), we'll cache it to disk. If POIs are sparse, we'll expand the search radius.
