# RouteIQ — Engineering Learnings

Key technical learnings from building a GraphRAG scenic route assistant.
Written for the project submission Google Doc.

---

## RAG Data Quality — Wikipedia Enrichment

### Broad OSM tag sweeps break enrichment pipelines

**What happened:** Querying OSMnx with `historic: True` returns every OSM feature with
any `historic` key — county boundaries, historic roads, unnamed districts, and minor
buildings — not just named landmarks. The result was hundreds of features, almost none
with a `wikipedia` OSM tag. When these POIs hit the Wikipedia enrichment step, the
name-based opensearch fallback matched generic names like "Old County Road" to completely
unrelated or disambiguation articles with empty extracts. All descriptions returned `None`,
causing the entire route result to be discarded.

**Fix:** Replaced the broad `historic: True` with an explicit allowlist of subtypes that
reliably map to Wikipedia articles: `castle`, `fort`, `monument`, `memorial`, `ruins`,
`archaeological_site`, `lighthouse`, `manor`, `battlefield`.

**Learning:** In geospatial RAG, input quality gates matter as much as the retrieval
pipeline. A broad OSM tag sweep creates garbage-in-garbage-out that vector similarity
or graph augmentation cannot recover from downstream. Be specific about what you ingest.

---

### Generic entity names produce wrong Wikipedia articles

**What happened:** The MediaWiki opensearch fallback (fired for POIs with no `wikipedia`
OSM tag) matched "Lighthouse" to the generic Wikipedia article on lighthouse architecture,
not a specific California lighthouse. The `extract` field was empty or off-topic for most
generic POI names along a route corridor.

**Fix:** Appended geographic context to the search: `f"{poi.name} California"`.
"Point Bonita Lighthouse California" resolves directly to the correct article.

**Learning:** Enrichment pipelines need disambiguation context, not just the raw entity
name. For geospatial POIs, appending state or region is a cheap, high-signal fix. The
broader principle: when resolving entity names to knowledge sources, always include the
minimal context needed to disambiguate.

---

### Silent API timeouts made enrichment failures invisible

**What happened:** A 5-second timeout on Wikipedia API calls caused requests to time out
silently under load (caught by `except Exception: pass`). `poi.description` stayed `None`
with no log entry and no signal to the caller that anything had failed.

**Fix:** Raised timeout to 15 seconds.

**Learning:** Silent exception swallowing in enrichment loops is dangerous — it turns
external API degradation into mysterious data quality failures. At minimum, count and
surface timeout rates so you can distinguish "Wikipedia has no article for this POI" from
"Wikipedia API was slow and we gave up too early."

---

### Hard description gate converted partial failures into total failures

**What happened:** The RAG node filtered out POIs with empty descriptions, then triggered
a full `no_pois_found` fallback if all were filtered. When Wikipedia enrichment failed for
every POI (due to the above bugs), the entire route result was discarded — even though the
graph layer had correctly found real, named landmarks along the route.

**Fix:** Removed the hard filter. POIs with no description are kept and passed to Claude
with `name + category + detour_min`. Claude narrates from available data without
fabricating details.

**Learning:** RAG pipeline failures should degrade gracefully, not propagate as hard
errors. Partial enrichment is far more useful than a full fallback. Each stage should
pass forward whatever it has, and the LLM at the end can handle missing context far
better than a binary "no data available" message implies.

---

## GraphRAG — Knowledge Graph Design

### 3-stage KnowledgeRAG pipeline

The GraphRAG layer (`KnowledgeRAG`) runs three stages in sequence:

1. **Vector retrieval** — ChromaDB semantic search over POI text chunks finds candidates
   by description similarity to the user's preferences.
2. **Graph filter + augment** — `RouteKnowledgeGraph` (NetworkX in-memory) filters
   candidates to those geographically near the route corridor and augments each with
   graph-derived context: which region it belongs to (`IN_REGION`), its category
   (`HAS_CATEGORY`), and nearby POIs (`NEAR_POI`).
3. **Context assembly** — Augmented candidates are formatted into a rich context string
   that Claude uses for narrative generation.

This design is the core of the GraphRAG approach: semantic search narrows the candidate
set, then graph traversal adds spatial and relational precision that embeddings alone
cannot provide.

---

### Typed edge relationships are what make it a knowledge graph

`RouteKnowledgeGraph` uses four typed edge relationships:

| Edge | Connects | Purpose |
|------|----------|---------|
| `LOCATED_IN` | POI → City | Enables "near San Francisco" filtering |
| `HAS_CATEGORY` | POI → Category | Enables preference-based filtering ("wineries") |
| `IN_REGION` | POI/City → Region | Enables broad corridor matching ("Bay Area") |
| `NEAR_POI` | POI → POI | Enables "also nearby" co-recommendations |

**Learning:** Typed edges are what distinguish a knowledge graph from a plain adjacency
list. They enable multi-hop reasoning ("find POIs in a region that match a category that
are near another POI on the route") which vector similarity cannot express. Even a small,
manually-seeded knowledge graph adds precision that no embedding model can replicate.

---

### KnowledgeGraph seed data vs live OSM data — the coverage gap

**Design tension:** The KnowledgeGraph is pre-seeded with 15 Bay Area landmark POIs and
8 cities. Live queries pull OSM features that may not exist in the seed data. When a
live OSM POI has no matching node in the knowledge graph, the graph augmentation step
returns no relational context.

**How it's handled:** `KnowledgeRAG` falls back to plain vector context for POIs not in
the knowledge graph. Famous Bay Area landmarks (Point Lobos, Muir Woods) get the full
3-stage treatment; obscure OSM features get vector-only context.

**Learning:** GraphRAG is only as powerful as its knowledge graph coverage. For a Week 1
project, the practical strategy is: seed the KG with landmarks most likely to appear in
demo queries, accept graceful degradation for everything else, and expand iteratively
based on which queries fail. Don't try to ingest all of OSM into the KG upfront —
coverage debt is manageable, but a slow or broken KG destroys the whole system.

---

### POI chunking strategy: precision vs recall tradeoff

`POIChunker` splits POI descriptions into 250-character chunks with 20-character overlap
before indexing in ChromaDB. Whole-document indexing was tried first but made similarity
scores less discriminative — a 500-character description covers multiple facts, making
the embedding an average that doesn't match any specific user preference well.

250-character chunks are more semantically coherent around a single aspect of a landmark.
`get_parent_osm_id()` in the chunk metadata reconstructs the parent POI so the upstream
graph augmentation step can still work on the full entity.

**Learning:** Chunk size in RAG is a precision vs recall tradeoff. For short POI
descriptions (100–500 chars), 250-character chunks with overlap hit the right balance.
For longer documents, this would need to be tuned. The chunk-to-parent ID mapping is
essential — without it, chunking breaks the graph augmentation step.

---

## LangGraph Pipeline

### LLM output formatting breaks structured data extraction

**What happened:** Claude's `QueryParser` returned JSON wrapped in ` ```json ... ``` `
markdown fences, which `json.loads()` rejected with a `JSONDecodeError`. Every query
failed at the parse step until this was caught.

**Fix:** Strip markdown fences with `re.sub` before parsing:
```python
text = re.sub(r"^```[a-z]*\n?", "", text.strip())
text = re.sub(r"\n?```$", "", text)
```

**Learning:** When extracting structured data from LLM output, always assume the model
may add formatting — markdown fences, prose prefixes, trailing explanation. Strip
aggressively before parsing. Include explicit instructions in the prompt: "return raw
JSON only, no markdown fences, no explanation." Even with instructions, defensive
stripping is still the right engineering practice.

---

## GraphRAG vs Vector Baseline — Key Finding

GraphRAG wins on route-constrained queries because the graph layer adds geographic
precision that vector similarity cannot replicate. A vector search for "coastal California
lighthouse" returns Pigeon Point Lighthouse regardless of whether it's on your route;
GraphRAG only surfaces it if it falls within the shape-buffer corridor around the A* path.

Vector search wins on open-ended semantic queries ("beautiful coastal drives") where there
is no route to constrain — the graph layer has nothing to operate on, and pure semantic
recall over POI descriptions is the right tool.

**The core insight:** GraphRAG and vector search are not competing approaches — they are
complementary. Route-specified queries (`"Drive from A to B, show X"`) benefit from graph
constraints; open-ended discovery queries (`"best X near Y"`) benefit from pure semantic
recall. A production system would classify query intent first and dispatch accordingly.
This is validated by the evaluation in `eval/results.md`: 6/6 GraphRAG wins on route
queries, 4/4 vector wins on semantic queries, 10/10 total prediction accuracy.
