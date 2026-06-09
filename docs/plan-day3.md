# Day 3 — RAG Layer: Wikipedia Enrichment + ChromaDB + Vector Baseline

## Goal
Build the full RAG layer: enrich POIs with Wikipedia text and thumbnail images, index them
in ChromaDB for semantic retrieval, implement the vector-only baseline for Day 4 evaluation,
and wire everything into the pipeline so Claude generates narratives grounded in Wikipedia.

---

## Files created

```
routeiq/graph/poi.py              added: description field
routeiq/rag/
  wikipedia_fetcher.py            WikipediaFetcher (Strategy)
  poi_indexer.py                  POIIndexer (Registry)
  poi_retriever.py                POIRetriever (Facade)
  vector_baseline.py              VectorBaseline (Strategy)
  __init__.py                     re-exports all 4

routeiq/insights/prompts/
  narrative.py                    added NARRATIVE_PROMPT_V2 (active)

routeiq/insights/
  narrative_chain.py              updated: poi_context kwarg added

routeiq/pipeline.py               _rag_node fully implemented
routeiq/facade.py                 wires WikipediaFetcher, POIIndexer, POIRetriever

tests/
  test_wikipedia_fetcher.py       (11 tests)
  test_poi_indexer.py             (8 tests)
  test_poi_retriever.py           (4 tests)
  test_vector_baseline.py         (5 tests)

day3_verify.py
```

---

## Step 1 — Add description field to POI

```python
# routeiq/graph/poi.py — add after image_url:
description: str | None = None   # Wikipedia extract, populated Day 3
```

---

## Step 2 — WikipediaFetcher (Strategy pattern)

**File:** `routeiq/rag/wikipedia_fetcher.py`

**Design:**
- Uses Wikipedia REST API: `https://en.wikipedia.org/api/rest_v1/page/summary/{title}`
- Accepts an injectable `requests.Session` for testability
- Title resolution priority:
  1. OSM `wikipedia` tag (format `"en:Title"` or `"Title"`)
  2. Fallback: MediaWiki opensearch API
- Mutates POI in-place — never raises, always degrades gracefully

**Key constants:**
```python
_DESCRIPTION_MAX_CHARS = 500    # truncate long extracts
_REQUEST_TIMEOUT = 5            # seconds
```

**`enrich(poi: POI) → None`:**
```python
title = self._resolve_title(poi)
# GET /api/rest_v1/page/summary/{title}
# → poi.description = data["extract"][:500]
# → poi.image_url   = data["thumbnail"]["source"]
# On 404, timeout, or any exception: pass (no mutation)
```

**`_resolve_title(poi) → str | None`:**
```python
if poi.wikipedia_tag:
    return tag.split(":", 1)[-1]   # strips "en:" prefix
# fallback: MediaWiki opensearch
# GET /w/api.php?action=opensearch&search={poi.name}&limit=1
# returns [query, [titles], [descriptions], [urls]]
# return titles[0] if titles else None
```

---

## Step 3 — POIIndexer (Registry pattern)

**File:** `routeiq/rag/poi_indexer.py`

**Design:**
- `chromadb.PersistentClient(path="./cache/chroma")` for production
- `collection_name` parameter — **CRITICAL: always use uuid-suffixed name in tests**
- Only indexes POIs that have `description` — skips others
- `upsert` = idempotent (same osm_id → overwrites)

```python
class POIIndexer:
    def __init__(self, client=None, persist_dir="./cache/chroma",
                 collection_name=_DEFAULT_COLLECTION):
        self._client = client or chromadb.PersistentClient(path=persist_dir)
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(collection_name)

    def index(self, pois: list[POI]) -> int:
        enriched = [p for p in pois if p.description]
        if not enriched:
            return 0
        self._collection.upsert(
            ids=[p.osm_id for p in enriched],
            documents=[p.description for p in enriched],
            metadatas=[{"name": p.name, "category": p.category,
                        "lat": p.lat, "lon": p.lon, "image_url": p.image_url or ""}
                       for p in enriched],
        )
        return len(enriched)

    def clear(self):
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(self._collection_name)
```

**Test isolation pattern (mandatory):**
```python
def _ephemeral_indexer():
    client = chromadb.EphemeralClient()
    return POIIndexer(client=client, collection_name=f"test_{uuid.uuid4().hex}")
```
ChromaDB `EphemeralClient()` shares in-memory state within a process.
UUID collection names prevent test-to-test data bleed.

---

## Step 4 — POIRetriever (Facade pattern)

**File:** `routeiq/rag/poi_retriever.py`

```python
class POIRetriever:
    def __init__(self, indexer: POIIndexer):
        self._collection = indexer.collection

    def get_context(self, osm_ids: list[str]) -> dict[str, str]:
        # returns {osm_id: description}, missing IDs omitted
        if not osm_ids:
            return {}
        try:
            result = self._collection.get(ids=osm_ids, include=["documents"])
            return {id_: doc for id_, doc in zip(result["ids"], result["documents"]) if doc}
        except Exception:
            return {}   # graceful on unknown IDs or collection errors
```

---

## Step 5 — VectorBaseline (Strategy pattern)

**File:** `routeiq/rag/vector_baseline.py`

**Purpose:** Pure semantic retrieval, no graph constraints. Used in Day 4
10-query comparison: GraphRAG results vs. this vector-only baseline.

```python
class VectorBaseline:
    def query(self, text: str, n_results: int = 5) -> list[dict]:
        count = self._collection.count()
        if count == 0:
            return []
        k = min(n_results, count)
        results = self._collection.query(
            query_texts=[text], n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "name": meta["name"], "category": meta["category"],
                "description": doc,
                "similarity_score": round(1.0 - dist, 4),   # cosine: 1 - distance
            }
            for meta, doc, dist in zip(
                results["metadatas"][0], results["documents"][0], results["distances"][0]
            )
        ]
```

`similarity_score = 1.0 - cosine_distance` → range roughly [-1, 1], higher = more similar.

---

## Step 6 — Update narrative prompt to V2

**File:** `routeiq/insights/prompts/narrative.py`

V2 additions vs V1:
- Explicitly notes context is Wikipedia-enriched
- Each stop entry format: `name | category | detour time | description`
- Instructs Claude to ground every fact in provided descriptions
- Handles case where stop has no description (use name + category only)

```python
NARRATIVE_PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """...
Each stop entry is formatted as:
  name | category | detour time | description

Instructions:
- Write an engaging opening narrative (3-5 sentences)
- List each stop: name | detour time | one sentence why to visit
- Ground every recommendation in the provided descriptions — do not invent facts.
- If a stop has no description, rely on the category and name only."""),
])
NARRATIVE_PROMPT = NARRATIVE_PROMPT_V2   # V1 preserved for reference
```

---

## Step 7 — Update NarrativeChain

Add `poi_context: str | None = None` as a keyword-only parameter:
```python
def generate(self, ..., *, poi_context: str | None = None) -> str:
    return self._chain.invoke({
        ...,
        "poi_context": poi_context if poi_context is not None
                       else self._format_poi_context(top_pois),
    })
```
Backward-compatible: existing call sites that don't pass `poi_context` still work.

---

## Step 8 — Implement `_rag_node` in pipeline

```python
def _rag_node(self, state: PipelineState) -> dict:
    if not state.get("top_pois"):
        return {"error": "no_pois_found", "fallback_reason": "..."}

    top_pois = state["top_pois"]

    # 1. Wikipedia enrichment (if fetcher wired)
    if self._wikipedia_fetcher:
        for sp in top_pois:
            self._wikipedia_fetcher.enrich(sp.poi)

    # 2. ChromaDB indexing (if indexer wired)
    if self._poi_indexer:
        self._poi_indexer.index([sp.poi for sp in top_pois])

    # 3. Build poi_context string for narrative prompt
    poi_context = self._build_poi_context(top_pois)
    return {"poi_context": poi_context}

@staticmethod
def _build_poi_context(top_pois) -> str:
    lines = []
    for sp in top_pois:
        p = sp.poi
        desc = p.description or "(no description available)"
        lines.append(
            f"{p.name} | {p.category} | {sp.detour_min:.0f} min detour | {desc}"
        )
    return "\n\n".join(lines)
```

Add `wikipedia_fetcher`, `poi_indexer`, `poi_retriever` as optional constructor params.

---

## Step 9 — Update facade

Wire all RAG components with optional DI:
```python
_indexer = poi_indexer or POIIndexer()
RoutePipeline(
    ...
    wikipedia_fetcher=wikipedia_fetcher or WikipediaFetcher(),
    poi_indexer=_indexer,
    poi_retriever=poi_retriever or POIRetriever(_indexer),
)
```

---

## Step 10 — Update existing pipeline test

The test `test_with_top_pois_is_pass_through` asserted `result == {}`.
After Day 3, `_rag_node` returns `{"poi_context": ...}`. Update to:
```python
def test_with_top_pois_sets_poi_context(self):
    result = p._rag_node(state)
    assert "poi_context" in result
    assert "Alamo" in result["poi_context"]
```

---

## Step 11 — Tests

**`test_wikipedia_fetcher.py`** (11 tests)
- `_resolve_title`: wikipedia tag with/without prefix, opensearch fallback,
  empty results, network error
- `enrich`: sets description+image_url, truncates long extract,
  no title → no mutation, non-200 response, network exception, no thumbnail

**`test_poi_indexer.py`** (8 tests)
- indexes POI with description, skips without, indexes only those with descriptions
- upsert is idempotent, metadata stores image_url, empty string when no image_url
- empty list → 0, clear() resets collection

**`test_poi_retriever.py`** (4 tests)
- returns description for indexed POI
- multiple IDs returned
- unknown ID omitted (exception caught)
- empty IDs → {}

**`test_vector_baseline.py`** (5 tests)
- empty collection → []
- returns results for indexed POIs
- n_results cap respected
- n_results capped at collection size
- result has required keys (name, category, description, similarity_score)

---

## Step 12 — day3_verify.py (5-step script)

```
Step 1: WikipediaFetcher — enrich 3 sample POIs (Alamo, Natural Bridge Caverns, Enchanted Rock)
Step 2: POIIndexer — index enriched POIs into ChromaDB EphemeralClient
Step 3: POIRetriever — retrieve contexts by osm_id
Step 4: VectorBaseline — query with 3 sample queries, print ranked results
Step 5: Pipeline simulation — call RoutePipeline._build_poi_context() directly, print output
```

Runs with real Wikipedia network calls. No ANTHROPIC_API_KEY needed.

---

## Key gotchas

| Gotcha | Detail |
|--------|--------|
| EphemeralClient shared state | Chromadb EphemeralClient shares in-memory store within process. Always use `uuid.uuid4().hex` suffix on collection name in tests |
| Cosine distance range | ChromaDB returns cosine *distance* (0=identical, 2=opposite). `similarity = 1.0 - distance` can be negative for dissimilar items |
| Upsert vs insert | `collection.upsert()` handles both new and existing ids — idempotent |
| `poi_context` is None vs empty string | `if poi_context is not None` — empty string is valid (no POIs), None means "not set, use fallback format" |

---

## Verification

```bash
python3 -m pytest tests/ -v      # 101 tests passing (Days 1+2+3)
python3 day3_verify.py           # requires network (Wikipedia API calls)
```
