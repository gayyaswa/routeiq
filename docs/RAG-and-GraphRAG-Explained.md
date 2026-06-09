# RAG and GraphRAG — What They Give RouteIQ

A first-principles explanation of vector RAG, Knowledge Graph RAG, and why chunking is needed,
using RouteIQ as the concrete example throughout. Written for project submission.

---

## The core problem RAG solves

Claude (or any LLM) has two fundamental limitations:

1. **Knowledge cutoff** — it was trained on data up to a date. The Alamo exists in its weights, but your specific POI list, detour scores, and Wikipedia fetches do not.
2. **Context is the only truth** — whatever you put in the prompt is what the model reasons from. If it's not in the prompt, the model invents (hallucinates) or hedges.

RAG ("Retrieval-Augmented Generation") is the pattern of: **fetch relevant facts at query time, inject them into the prompt, let the model reason over facts it can actually see.**

Without RAG, Claude's narrative prompt would be:
```
"Generate a scenic route from Austin to San Antonio with historic stops"
```
Claude would make up plausible-sounding stops from training memory. With RAG, you inject:
```
"The Alamo | mission | 0 min detour | Built in 1718, site of the 1836 Battle..."
"Mission Concepción | mission | 4 min detour | Oldest unrestored stone church..."
```
Now Claude reasons over facts you retrieved, not facts it remembered. That's the entire value proposition.

---

## Layer 1 — Vector RAG: what it gives RouteIQ

### How it works

Every piece of text can be converted to a vector (a list of ~1500 numbers) by an embedding model. Semantically similar texts produce numerically close vectors. ChromaDB stores these vectors and can find the closest ones to a query vector.

```
"historic missions Texas"  →  [0.23, -0.81, 0.44, ...]   ← query vector
"The Alamo, 1718, Spanish colonial mission..."  →  [0.21, -0.79, 0.46, ...]   ← close
"Canyon Lake, recreational reservoir..."  →  [-0.62, 0.33, -0.11, ...]   ← far
```

ChromaDB returns the top-K closest documents by cosine distance. That's Stage 1 in KnowledgeRAG, and it's what `VectorBaseline` does end-to-end.

### What intelligence vector RAG adds to RouteIQ

**Semantic matching without exact keywords.** If the user says "I want spiritual and historic places", vector search finds "The Alamo" and "Mission Concepción" even though neither of those words appears in the query. The embedding space captures meaning, not spelling.

**Wikipedia description surfacing.** Without RAG, the narrative prompt only has the POI name and category. With vector RAG, the prompt contains the actual Wikipedia extract — "Built in 1718 as a Spanish colonial mission... 1836 Battle of the Alamo..." — so Claude's narrative is grounded in real facts, not invented ones.

**Ranking by relevance.** If you have 50 indexed POIs but the user asked for wineries, vector search returns Becker Vineyards ranked above The Alamo. The model gets the most query-relevant facts first.

### What vector RAG cannot do

It is **semantically smart but spatially blind**. Vector search doesn't know that Enchanted Rock is in Fredericksburg. It doesn't know that Fredericksburg is in the Hill Country. It doesn't know which POIs are actually along your route. It just returns the chunks whose text is most similar to your query, regardless of geography or relationships.

If you ask for "natural outdoor experiences", vector search might return Enchanted Rock (which is 100 km off the Austin→San Antonio route) ranked above Mission Concepción (which is directly on it). The model then confidently narrates a stop that would add 2 hours of detour.

---

## Layer 2 — Knowledge Graph RAG: what it adds

### What a knowledge graph is

A knowledge graph stores entities as **nodes** and facts about them as **typed edges**. The key word is *typed* — the relationship label carries meaning.

In RouteIQ's NetworkX DiGraph:

```
kg_alamo  ──[LOCATED_IN]──►  San Antonio
kg_alamo  ──[HAS_CATEGORY]──►  mission
San Antonio  ──[IN_REGION]──►  San Antonio Missions
kg_alamo  ──[NEAR_POI]──►  kg_concepcion   (dist: 2.4 km)
kg_alamo  ──[NEAR_POI]──►  kg_sanjuan      (dist: 7.1 km)
```

This is structured, queryable knowledge — not prose that a model has to interpret. You can ask "what city is this POI in?" and get a deterministic answer by traversing an edge.

### The 3-stage pipeline and what each stage contributes

**Stage 1 — Vector search (same as pure vector RAG)**

Embed user preferences → find semantically matching chunks in ChromaDB. Returns ranked candidates with evidence text. This is the semantic intelligence layer.

**Stage 2 — Graph filter + augment (the GraphRAG addition)**

*Filter:* `get_pois_for_route(route_coords)` builds a bounding box around your route, finds which City nodes fall inside it, then returns only POIs whose `LOCATED_IN` edge points to one of those cities. This eliminates Enchanted Rock (Fredericksburg is outside the Austin→San Antonio bbox) and keeps The Alamo (San Antonio is inside it).

This is **deterministic spatial grounding** — not probability, not embedding distance, but a hard boolean filter based on geographic facts stored as graph edges.

*Augment:* `enrich_poi(osm_id)` traverses the graph and returns:
```python
{
    "city": "San Antonio",            # LOCATED_IN traversal
    "region": "San Antonio Missions", # LOCATED_IN → IN_REGION traversal
    "category": "mission",            # HAS_CATEGORY traversal
    "nearby_pois": ["Mission Concepción", "Mission San Juan"]  # NEAR_POI traversal
}
```

This structured data goes into the Stage 3 context string, which goes into the Claude prompt. Now Claude knows not just what the POI is (from Wikipedia text) but **where it sits in the world's structure** — what city, what named region, what other stops are nearby.

**Stage 3 — Context build**

Formats the enriched data as:
```
The Alamo | mission | San Antonio | San Antonio Missions | nearby: Mission Concepción, Mission San Juan | Built in 1718...
```

The narrative prompt (`NARRATIVE_PROMPT_V3`) tells Claude: "mention the region where it adds flavour" — so it can write "deep in the San Antonio Missions district" grounded in graph traversal, not guessed from training data.

### What GraphRAG gives that pure vector cannot

| Capability | Vector RAG | Knowledge Graph RAG |
|---|---|---|
| Semantic matching | Yes | Yes (Stage 1) |
| Grounded descriptions | Yes | Yes |
| Spatial filtering (is this stop on my route?) | No | Yes (Stage 2 filter) |
| Relationship context (what region, what nearby stops?) | No | Yes (Stage 2 augment) |
| Deterministic answers | No | Yes (graph traversal) |
| Handles "nearby" queries | No | Yes (NEAR_POI edges) |

The single biggest win: **a stop that scores high semantically but is geographically wrong gets filtered out.** With pure vector RAG, Enchanted Rock might rank #1 for "natural outdoors" on an Austin→San Antonio query and Claude would confidently recommend a 100 km detour. With GraphRAG, it's gone by the end of Stage 2.

---

## Why chunking is needed

### The problem with indexing full documents

Suppose The Alamo's Wikipedia article is 800 words (roughly 5000 characters). ChromaDB converts that entire article into **one vector** — a single point in embedding space. That point represents the "average meaning" of all 800 words.

Now consider two users:
- User A asks: "Tell me about the 1836 battle"
- User B asks: "Is The Alamo a UNESCO site?"

Both are about The Alamo. But the battle is covered in paragraph 2, and the UNESCO designation is in paragraph 6. A single 800-word vector averages everything together — it's approximately equally close to both queries, but not maximally close to either. The retrieval is imprecise.

### What chunking does

Splitting into 250-character chunks means:
```
chunk_0: "The Alamo is a historic Spanish colonial mission in San Antonio..."
chunk_1: "It was the site of the 1836 Battle of the Alamo, where Texian defenders..."
chunk_2: "Today it is a UNESCO World Heritage Site and the most visited..."
```

Each chunk gets its own vector. Now:
- User A's query embeds close to `chunk_1` (battle text)
- User B's query embeds close to `chunk_2` (UNESCO text)

**Retrieval precision improves dramatically.** The model gets the specific passage that answers the question, not an average of everything.

### The overlap (20 characters)

Sentences don't split cleanly at 250-char boundaries. "Mexican forces for 13 days. Today it is a UNESCO..." might get cut in the middle of a thought. The 20-char overlap means the end of `chunk_1` repeats at the start of `chunk_2`, so no sentence is orphaned and no context is lost at a boundary.

### The traceability problem chunking creates

When ChromaDB returns `kg_alamo_chunk_1`, you need to know that this came from The Alamo so you can:
1. Traverse the knowledge graph from `kg_alamo` to get city/region/nearby
2. Show the correct POI stop card in the UI

That's why `POIChunker` creates IDs like `kg_alamo_chunk_1`, and `get_parent_osm_id("kg_alamo_chunk_1")` → `"kg_alamo"` links the chunk back to the parent entity. This is the `Chunk -[PART_OF]-> Candidate` pattern from the course demo — the chunk carries a foreign key to its parent node.

---

## The full intelligence stack in RouteIQ

Here's what each layer contributes to a single query result:

```
User: "Austin to San Antonio, show me historic missions"

OSMnx + A*           → the actual road route (spatial truth)
DetourScorer         → how far each POI is from the route (geometric truth)
POISelector          → top-N stops by detour cost + category preference
WikipediaFetcher     → real description text per POI (factual truth, live-fetched)
POIChunker           → precise passage-level retrieval units
Stage 1 vector       → which POIs match "historic missions" semantically
Stage 2 graph filter → which of those are actually on the Austin→SA route
Stage 2 augment      → city, region, nearby stops for each surviving POI
Stage 3 context      → structured prompt context Claude can reason over
Claude V3 prompt     → narrative grounded in real facts, real geography, real structure
```

Each layer eliminates a different class of error:

| Without this layer | Error class eliminated |
|---|---|
| Spatial routing | Wrong road, wrong path |
| Detour scoring | Stops that add 3 hours of driving |
| Wikipedia RAG | Hallucinated descriptions |
| Chunking | Imprecise passage retrieval — wrong part of article surfaced |
| Graph filter | Semantically good but geographically wrong stops |
| Graph augment | Claude can't mention regions or nearby clusters |
| Structured prompt | Claude ignores context and improvises |

The combination is what makes GraphRAG meaningfully better than a bare LLM call or even a pure vector retrieval system — each layer adds a different kind of correctness guarantee.

---

## When GraphRAG wins vs. when vector-only is enough

GraphRAG beats vector-only when:
- **Spatial correctness matters** — you need stops on the actual route, not just semantically similar stops anywhere
- **Relationship context improves the answer** — knowing a stop is "in the Hill Country" or "near Enchanted Rock" makes the narrative richer and more accurate
- **You have structured knowledge** — city/region/category relationships are facts, not prose

Vector-only is sufficient when:
- The corpus is small and all results are plausible answers
- Geography is irrelevant (e.g. "what are good restaurants in this list?")
- You don't have a knowledge graph to traverse

For RouteIQ specifically: a pure vector baseline would produce good descriptions but wrong geography. GraphRAG produces good descriptions AND correct geography. The 10-query evaluation (Day 4) quantifies exactly how often the spatial filter changes the result set.
