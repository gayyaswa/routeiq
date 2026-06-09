# Session 4 Handoff — RouteIQ

## Start of next session
Say: `"continue from handoff, implement knowledge graph layer"`

---

## Current state

**Branch:** `feat/days-1-3-graph-rag-pipeline` — pushed to https://github.com/gayyaswa/routeiq  
**Tests:** 101/101 passing  
**Days complete:** Day 1 (graph), Day 2 (pipeline), Day 3 (RAG layer)

---

## Why we need the knowledge graph layer

The course demo (Project 3: GraphRAG for Org Knowledge) uses a 3-stage pipeline:

```
Stage 1 — Vector Search:   embed query → find semantically similar Chunk nodes
Stage 2 — Graph Filter:    filter by typed relationship (WORKED_AT company)
           + Augment:      traverse HAS_SKILL → collect structured entity data
Stage 3 — LLM Synthesis:   enriched context → GPT-4o-mini recommendation
```

RouteIQ today does: `road graph → spatial buffer → Wikipedia fetch → Claude narrative`  
The graph is a **road network** (navigation), not a **knowledge graph** (entity relationships).  
The course expects typed entity nodes + relationships. We're missing that layer.

**What we need to add:** A NetworkX knowledge graph (no Neo4j needed) with POI/City/Region/Category nodes and typed relationships, plus a KnowledgeRAG class that runs the 3-stage pipeline.

---

## Full implementation plan

### New files to create (in this order)

#### 1. `routeiq/graph/knowledge_graph_data.py`
Pure seed data — no logic. Copy this exactly:

```python
"""Seed data for the RouteIQ knowledge graph — POIs, Cities, Regions, Categories."""

CATEGORIES = [
    {"name": "historic"},
    {"name": "natural"},
    {"name": "tourism"},
    {"name": "winery"},
    {"name": "state_park"},
    {"name": "mission"},
]

REGIONS = [
    {"name": "Hill Country",           "type": "scenic_region"},
    {"name": "Highland Lakes",         "type": "scenic_region"},
    {"name": "San Antonio Missions",   "type": "historic_district"},
    {"name": "Blanco Valley",          "type": "scenic_region"},
    {"name": "Texas Wine Country",     "type": "scenic_region"},
]

CITIES = [
    {"name": "Austin",         "lat": 30.2672, "lon": -97.7431},
    {"name": "San Antonio",    "lat": 29.4241, "lon": -98.4936},
    {"name": "New Braunfels",  "lat": 29.7030, "lon": -98.1245},
    {"name": "San Marcos",     "lat": 29.8833, "lon": -97.9414},
    {"name": "Fredericksburg", "lat": 30.2752, "lon": -98.8720},
    {"name": "Kerrville",      "lat": 30.0474, "lon": -99.1403},
    {"name": "Marble Falls",   "lat": 30.5782, "lon": -98.2737},
    {"name": "Round Rock",     "lat": 30.5083, "lon": -97.6789},
]

POIS = [
    {
        "osm_id": "kg_alamo",
        "name": "The Alamo",
        "category": "mission",
        "lat": 29.4260, "lon": -98.4861,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:The Alamo",
    },
    {
        "osm_id": "kg_concepcion",
        "name": "Mission Concepción",
        "category": "mission",
        "lat": 29.4063, "lon": -98.4874,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:Mission Concepción",
    },
    {
        "osm_id": "kg_sanjuan",
        "name": "Mission San Juan",
        "category": "mission",
        "lat": 29.3630, "lon": -98.4815,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:Mission San Juan Capistrano (Texas)",
    },
    {
        "osm_id": "kg_natural_bridge",
        "name": "Natural Bridge Caverns",
        "category": "tourism",
        "lat": 29.6927, "lon": -98.3419,
        "city": "New Braunfels",
        "region": "Hill Country",
        "wikipedia_tag": "en:Natural Bridge Caverns",
    },
    {
        "osm_id": "kg_enchanted_rock",
        "name": "Enchanted Rock",
        "category": "natural",
        "lat": 30.5063, "lon": -98.8198,
        "city": "Fredericksburg",
        "region": "Hill Country",
        "wikipedia_tag": "en:Enchanted Rock",
    },
    {
        "osm_id": "kg_luckenbach",
        "name": "Luckenbach Texas",
        "category": "tourism",
        "lat": 30.1849, "lon": -98.7384,
        "city": "Fredericksburg",
        "region": "Texas Wine Country",
        "wikipedia_tag": "en:Luckenbach, Texas",
    },
    {
        "osm_id": "kg_gruene",
        "name": "Gruene Historic District",
        "category": "historic",
        "lat": 29.7380, "lon": -98.1096,
        "city": "New Braunfels",
        "region": "Blanco Valley",
        "wikipedia_tag": "en:Gruene, Texas",
    },
    {
        "osm_id": "kg_pedernales",
        "name": "Pedernales Falls State Park",
        "category": "state_park",
        "lat": 30.3077, "lon": -98.2566,
        "city": "Marble Falls",
        "region": "Hill Country",
        "wikipedia_tag": "en:Pedernales Falls State Park",
    },
    {
        "osm_id": "kg_old_tunnel",
        "name": "Old Tunnel State Park",
        "category": "natural",
        "lat": 30.1716, "lon": -98.7505,
        "city": "Fredericksburg",
        "region": "Texas Wine Country",
        "wikipedia_tag": "en:Old Tunnel State Park",
    },
    {
        "osm_id": "kg_guadalupe",
        "name": "Guadalupe River State Park",
        "category": "state_park",
        "lat": 29.8472, "lon": -98.4896,
        "city": "New Braunfels",
        "region": "Hill Country",
        "wikipedia_tag": "en:Guadalupe River State Park",
    },
    {
        "osm_id": "kg_becker",
        "name": "Becker Vineyards",
        "category": "winery",
        "lat": 30.2208, "lon": -98.8661,
        "city": "Fredericksburg",
        "region": "Texas Wine Country",
        "wikipedia_tag": "en:Becker Vineyards",
    },
    {
        "osm_id": "kg_hamilton",
        "name": "Hamilton Pool Preserve",
        "category": "natural",
        "lat": 30.3427, "lon": -98.1269,
        "city": "Austin",
        "region": "Hill Country",
        "wikipedia_tag": "en:Hamilton Pool Preserve",
    },
    {
        "osm_id": "kg_wimberley",
        "name": "Wimberley",
        "category": "tourism",
        "lat": 29.9977, "lon": -98.0986,
        "city": "San Marcos",
        "region": "Blanco Valley",
        "wikipedia_tag": "en:Wimberley, Texas",
    },
    {
        "osm_id": "kg_national_museum",
        "name": "San Antonio Missions National Historical Park",
        "category": "historic",
        "lat": 29.3596, "lon": -98.4760,
        "city": "San Antonio",
        "region": "San Antonio Missions",
        "wikipedia_tag": "en:San Antonio Missions National Historical Park",
    },
    {
        "osm_id": "kg_canyon_lake",
        "name": "Canyon Lake",
        "category": "natural",
        "lat": 29.8716, "lon": -98.2617,
        "city": "New Braunfels",
        "region": "Highland Lakes",
        "wikipedia_tag": "en:Canyon Lake (Texas)",
    },
]

# Typed relationships: (source_id, rel_type, target_id)
# source/target ids are osm_id for POIs, name for City/Region/Category
RELATIONSHIPS = (
    # POI -[LOCATED_IN]→ City
    [("kg_alamo",           "LOCATED_IN", "San Antonio")]
  + [("kg_concepcion",      "LOCATED_IN", "San Antonio")]
  + [("kg_sanjuan",         "LOCATED_IN", "San Antonio")]
  + [("kg_national_museum", "LOCATED_IN", "San Antonio")]
  + [("kg_natural_bridge",  "LOCATED_IN", "New Braunfels")]
  + [("kg_gruene",          "LOCATED_IN", "New Braunfels")]
  + [("kg_guadalupe",       "LOCATED_IN", "New Braunfels")]
  + [("kg_canyon_lake",     "LOCATED_IN", "New Braunfels")]
  + [("kg_enchanted_rock",  "LOCATED_IN", "Fredericksburg")]
  + [("kg_luckenbach",      "LOCATED_IN", "Fredericksburg")]
  + [("kg_old_tunnel",      "LOCATED_IN", "Fredericksburg")]
  + [("kg_becker",          "LOCATED_IN", "Fredericksburg")]
  + [("kg_pedernales",      "LOCATED_IN", "Marble Falls")]
  + [("kg_hamilton",        "LOCATED_IN", "Austin")]
  + [("kg_wimberley",       "LOCATED_IN", "San Marcos")]
  # POI -[HAS_CATEGORY]→ Category
  + [(p["osm_id"], "HAS_CATEGORY", p["category"]) for p in POIS]
  # City -[IN_REGION]→ Region  (via POI region field)
  + [("San Antonio",    "IN_REGION", "San Antonio Missions")]
  + [("New Braunfels",  "IN_REGION", "Hill Country")]
  + [("Fredericksburg", "IN_REGION", "Hill Country")]
  + [("Fredericksburg", "IN_REGION", "Texas Wine Country")]
  + [("Marble Falls",   "IN_REGION", "Highland Lakes")]
  + [("San Marcos",     "IN_REGION", "Blanco Valley")]
  + [("Austin",         "IN_REGION", "Hill Country")]
)
```

---

#### 2. `routeiq/graph/knowledge_graph.py`

```python
"""NetworkX knowledge graph: POI/City/Region/Category nodes with typed edges (Registry pattern)."""
from __future__ import annotations
import math
from typing import Any
import networkx as nx
from routeiq.graph.knowledge_graph_data import POIS, CITIES, REGIONS, CATEGORIES, RELATIONSHIPS


class RouteKnowledgeGraph:
    """Builds and queries a knowledge graph of Texas scenic route entities (Registry pattern).

    Node types: POI, City, Region, Category
    Edge types: LOCATED_IN, HAS_CATEGORY, IN_REGION, NEAR_POI
    """

    _NEAR_POI_MAX_KM = 25.0  # two POIs are NEAR each other within this distance

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()
        self._build()

    @property
    def graph(self) -> nx.DiGraph:
        return self._g

    def enrich_poi(self, osm_id: str) -> dict:
        """Returns {city, region, category, nearby_poi_names} for a POI node."""
        if osm_id not in self._g:
            return {}
        city = self._first_neighbor(osm_id, "LOCATED_IN")
        region = self._first_neighbor(osm_id, "IN_REGION_VIA_CITY")
        category = self._first_neighbor(osm_id, "HAS_CATEGORY")
        nearby = [
            self._g.nodes[n]["name"]
            for n in self._g.successors(osm_id)
            if self._g.edges[osm_id, n].get("rel") == "NEAR_POI"
        ]
        return {"city": city, "region": region, "category": category, "nearby_pois": nearby}

    def get_pois_for_route(self, route_coords: list[tuple[float, float]]) -> list[str]:
        """Returns osm_ids of POIs whose city falls within the route bounding box (+0.3 deg pad)."""
        if not route_coords:
            return []
        lats = [c[0] for c in route_coords]
        lons = [c[1] for c in route_coords]
        pad = 0.3
        north, south = max(lats) + pad, min(lats) - pad
        east, west   = max(lons) + pad, min(lons) - pad

        on_route_cities = {
            n for n, d in self._g.nodes(data=True)
            if d.get("type") == "City"
            and south <= d["lat"] <= north
            and west  <= d["lon"] <= east
        }
        return [
            n for n, d in self._g.nodes(data=True)
            if d.get("type") == "POI"
            and self._city_for_poi(n) in on_route_cities
        ]

    def get_all_pois(self) -> list[str]:
        return [n for n, d in self._g.nodes(data=True) if d.get("type") == "POI"]

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    # ── private ────────────────────────────────────────────────────────────

    def _build(self) -> None:
        for cat in CATEGORIES:
            self._g.add_node(cat["name"], type="Category", name=cat["name"])
        for reg in REGIONS:
            self._g.add_node(reg["name"], type="Region", name=reg["name"])
        for city in CITIES:
            self._g.add_node(city["name"], type="City", **city)
        for poi in POIS:
            self._g.add_node(poi["osm_id"], type="POI", **poi)
        for src, rel, tgt in RELATIONSHIPS:
            self._g.add_edge(src, tgt, rel=rel)
        self._add_near_poi_edges()

    def _add_near_poi_edges(self) -> None:
        poi_nodes = [(n, d) for n, d in self._g.nodes(data=True) if d.get("type") == "POI"]
        for i, (id_a, d_a) in enumerate(poi_nodes):
            for id_b, d_b in poi_nodes[i + 1:]:
                dist = self._haversine(d_a["lat"], d_a["lon"], d_b["lat"], d_b["lon"])
                if dist <= self._NEAR_POI_MAX_KM:
                    self._g.add_edge(id_a, id_b, rel="NEAR_POI", dist_km=round(dist, 1))
                    self._g.add_edge(id_b, id_a, rel="NEAR_POI", dist_km=round(dist, 1))

    def _city_for_poi(self, osm_id: str) -> str | None:
        return self._first_neighbor(osm_id, "LOCATED_IN")

    def _first_neighbor(self, node_id: str, rel: str) -> str | None:
        for nbr in self._g.successors(node_id):
            if self._g.edges[node_id, nbr].get("rel") == rel:
                return self._g.nodes[nbr].get("name", nbr)
        return None

    def _in_region_via_city(self, osm_id: str) -> str | None:
        city = self._city_for_poi(osm_id)
        if not city:
            return None
        for nbr in self._g.successors(city):
            if self._g.edges[city, nbr].get("rel") == "IN_REGION":
                return self._g.nodes[nbr].get("name", nbr)
        return None

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
```

Fix `enrich_poi` — call `_in_region_via_city` not `_first_neighbor(osm_id, "IN_REGION_VIA_CITY")`:
```python
region = self._in_region_via_city(osm_id)
```

---

#### 3. `routeiq/rag/poi_chunker.py`

```python
"""Splits POI Wikipedia descriptions into chunks and indexes them (mirrors Chunk-PART_OF-Candidate)."""
from __future__ import annotations
from langchain_text_splitters import RecursiveCharacterTextSplitter
from routeiq.graph.poi import POI
from routeiq.rag.poi_indexer import POIIndexer

_CHUNK_SIZE    = 250   # matches course demo exactly
_CHUNK_OVERLAP = 20    # matches course demo exactly


class POIChunker:
    """Chunks POI descriptions and indexes them in ChromaDB with poi_osm_id metadata (Pipeline pattern).

    Mirrors the Chunk -[PART_OF]-> Candidate pattern from the course GraphRAG demo.
    """

    def __init__(self, indexer: POIIndexer) -> None:
        self._indexer = indexer
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP
        )

    def chunk_and_index(self, pois: list[POI]) -> int:
        """Splits each POI description into chunks, indexes all chunks. Returns chunk count."""
        total = 0
        for poi in pois:
            if not poi.description:
                continue
            chunks = self._splitter.split_text(poi.description)
            chunk_pois = []
            for i, chunk_text in enumerate(chunks):
                # Create a synthetic POI per chunk so POIIndexer can store it
                chunk_poi = POI(
                    name=poi.name,
                    category=poi.category,
                    lat=poi.lat,
                    lon=poi.lon,
                    osm_id=f"{poi.osm_id}_chunk_{i}",
                    description=chunk_text,
                    image_url=poi.image_url,
                )
                chunk_pois.append(chunk_poi)
            indexed = self._indexer.index(chunk_pois)
            total += indexed
        return total
```

Note: `POIIndexer` stores `poi_osm_id` prefix in the chunk id so we can trace back to the parent POI. Add a `get_parent_osm_id(chunk_id)` helper:
```python
@staticmethod
def get_parent_osm_id(chunk_id: str) -> str:
    """Extracts parent POI osm_id from a chunk id like 'kg_alamo_chunk_0'."""
    return chunk_id.rsplit("_chunk_", 1)[0]
```

---

#### 4. `routeiq/rag/knowledge_rag.py`

```python
"""3-stage GraphRAG pipeline: vector search → graph filter+augment → context (Pipeline pattern)."""
from __future__ import annotations
from routeiq.graph.knowledge_graph import RouteKnowledgeGraph
from routeiq.rag.poi_indexer import POIIndexer
from routeiq.rag.poi_chunker import POIChunker


class KnowledgeRAG:
    """Runs the 3-stage GraphRAG pipeline matching the course demo pattern (Pipeline pattern).

    Stage 1 — Vector search: embed preferences → find semantically similar chunks
    Stage 2 — Graph filter+augment: keep only on-route POIs, enrich with relationships
    Stage 3 — Build context: format enriched results for Claude narrative prompt
    """

    def __init__(self, indexer: POIIndexer, knowledge_graph: RouteKnowledgeGraph) -> None:
        self._collection = indexer.collection
        self._kg = knowledge_graph

    def query(
        self,
        preferences: list[str],
        route_coords: list[tuple[float, float]],
        n_candidates: int = 10,
    ) -> str:
        """Returns enriched poi_context string for the narrative prompt."""
        # Stage 1
        candidates = self._stage1_vector_search(preferences, n_candidates)
        if not candidates:
            return ""
        # Stage 2
        enriched = self._stage2_filter_augment(candidates, route_coords)
        if not enriched:
            return ""
        # Stage 3
        return self._stage3_build_context(enriched)

    def _stage1_vector_search(self, preferences: list[str], n: int) -> list[dict]:
        """Embed preferences → query ChromaDB chunks → return (parent_osm_id, score, evidence)."""
        if self._collection.count() == 0:
            return []
        query_text = " ".join(preferences) if preferences else "scenic landmark"
        k = min(n, self._collection.count())
        results = self._collection.query(
            query_texts=[query_text],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        seen_pois: dict[str, dict] = {}
        for chunk_id, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            parent_id = POIChunker.get_parent_osm_id(chunk_id)
            score = round(1.0 - dist, 4)
            if parent_id not in seen_pois or seen_pois[parent_id]["score"] < score:
                seen_pois[parent_id] = {
                    "osm_id": parent_id,
                    "name": meta.get("name", parent_id),
                    "score": score,
                    "evidence": doc,
                }
        return sorted(seen_pois.values(), key=lambda x: x["score"], reverse=True)

    def _stage2_filter_augment(
        self, candidates: list[dict], route_coords: list[tuple[float, float]]
    ) -> list[dict]:
        """Filter by ON_ROUTE, augment each candidate with knowledge graph relationships."""
        on_route_ids = set(self._kg.get_pois_for_route(route_coords))
        enriched = []
        for candidate in candidates:
            osm_id = candidate["osm_id"]
            # also accept kg_ prefixed POIs that match by prefix
            is_on_route = (
                osm_id in on_route_ids
                or any(r.startswith(osm_id) or osm_id.startswith(r) for r in on_route_ids)
            )
            if not is_on_route and on_route_ids:
                continue
            graph_data = self._kg.enrich_poi(osm_id)
            enriched.append({**candidate, **graph_data})
        return enriched

    def _stage3_build_context(self, enriched: list[dict]) -> str:
        """Format enriched POI data as context string for Claude (Stage 3 of course demo)."""
        lines = []
        for item in enriched:
            nearby = ", ".join(item.get("nearby_pois", [])[:3]) or "none"
            lines.append(
                f"{item['name']} | {item.get('category', '?')} | "
                f"{item.get('city', '?')} | {item.get('region', '?')} | "
                f"nearby: {nearby} | {item['evidence']}"
            )
        return "\n\n".join(lines)
```

---

#### 5. `routeiq/insights/prompts/narrative.py` — add V3

Add after V2:

```python
# V3 — Graph-enriched context: city, region, nearby POIs from knowledge graph traversal
NARRATIVE_PROMPT_V3 = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", """Generate a scenic route narrative for the following trip.

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
- Ground every fact in the provided context. Do not invent locations or distances."""),
])

NARRATIVE_PROMPT = NARRATIVE_PROMPT_V3  # active version
```

---

### Files to update

#### `routeiq/graph/__init__.py`
Add: `from routeiq.graph.knowledge_graph import RouteKnowledgeGraph`

#### `routeiq/rag/__init__.py`
Add: `from routeiq.rag.poi_chunker import POIChunker` and `from routeiq.rag.knowledge_rag import KnowledgeRAG`

#### `routeiq/pipeline.py` — update `_rag_node`

Replace the current `_rag_node` implementation with:

```python
def _rag_node(self, state: PipelineState) -> dict:
    if not state.get("top_pois"):
        return {
            "error": "no_pois_found",
            "fallback_reason": (
                f"No scenic stops found near the route from "
                f"{state['origin']} to {state['destination']}."
            ),
        }

    top_pois = state["top_pois"]

    # Enrich each POI with Wikipedia text + thumbnail
    if self._wikipedia_fetcher is not None:
        for sp in top_pois:
            self._wikipedia_fetcher.enrich(sp.poi)

    # If KnowledgeRAG is wired: run 3-stage pipeline (vector → graph → context)
    if self._knowledge_rag is not None:
        preferences = state.get("preferences") or []
        route_coords = state["route_result"].route_coords if state.get("route_result") else []

        # Index chunks for vector search (Stage 1 needs them)
        if self._poi_chunker is not None:
            pois = [sp.poi for sp in top_pois]
            self._poi_chunker.chunk_and_index(pois)

        poi_context = self._knowledge_rag.query(
            preferences=preferences,
            route_coords=route_coords,
        )
    else:
        # Fallback: plain context (Day 2/3 style)
        poi_context = self._build_poi_context(top_pois)

    return {"poi_context": poi_context}
```

Add `knowledge_rag`, `poi_chunker` to `RoutePipeline.__init__` params (optional, default None).

#### `routeiq/facade.py` — wire new components

```python
from routeiq.rag import WikipediaFetcher, POIIndexer, POIRetriever, KnowledgeRAG, POIChunker
from routeiq.graph import GraphLoader, POIFinder, RouteKnowledgeGraph

# In __init__:
_kg = RouteKnowledgeGraph()
_chunker_indexer = POIIndexer(collection_name="routeiq_chunks")
self._pipeline = RoutePipeline(
    ...
    wikipedia_fetcher=WikipediaFetcher(),
    poi_indexer=_chunker_indexer,
    poi_retriever=POIRetriever(_chunker_indexer),
    poi_chunker=POIChunker(_chunker_indexer),
    knowledge_rag=KnowledgeRAG(_chunker_indexer, _kg),
)
```

---

### Tests to write (3 new files)

**`tests/test_knowledge_graph.py`**
- `test_node_count_exceeds_20` — satisfies submission requirement
- `test_poi_has_located_in_city` — LOCATED_IN edge exists
- `test_poi_has_category` — HAS_CATEGORY edge exists
- `test_city_has_in_region` — IN_REGION edge exists
- `test_near_poi_edges_created` — NEAR_POI edges for close POIs
- `test_enrich_poi_returns_city_region_category`
- `test_get_pois_for_route_austin_sa` — Austin→SA bounding box returns SA missions
- `test_get_pois_for_route_empty_coords_returns_empty`

**`tests/test_poi_chunker.py`**
- `test_chunks_description_into_parts` — long text splits correctly
- `test_chunk_size_respected` — each chunk ≤ 250 chars
- `test_poi_without_description_skipped`
- `test_chunk_id_contains_parent_osm_id`
- `test_get_parent_osm_id_extracts_correctly`
- `test_indexes_all_chunks_to_chromadb`

**`tests/test_knowledge_rag.py`**
- `test_stage1_returns_ranked_candidates` — mock ChromaDB
- `test_stage2_filters_out_of_route_pois`
- `test_stage2_augments_with_city_and_region`
- `test_stage3_context_contains_name_category_region`
- `test_empty_collection_returns_empty_string`
- `test_no_route_coords_returns_all_candidates`

---

### Nebius (do after getting credentials)

In `routeiq/rag/poi_chunker.py` or `routeiq/rag/poi_indexer.py`, swap embeddings:

```python
# Today: ChromaDB default local embeddings
# After Nebius:
from langchain_community.embeddings import NebiusEmbeddings
nebius_embeddings = NebiusEmbeddings(
    model="BAAI/bge-en-icl",   # or whatever Nebius offers
    api_key=os.environ["NEBIUS_API_KEY"],
)
# Pass to ChromaDB collection via LangChain Chroma wrapper
```

---

### Implementation order for next session

```
1. knowledge_graph_data.py          (pure data, no deps)
2. knowledge_graph.py               (NetworkX, test immediately)
3. tests/test_knowledge_graph.py    (run, fix, confirm 20+ nodes)
4. poi_chunker.py                   (text splitter + ChromaDB)
5. tests/test_poi_chunker.py
6. knowledge_rag.py                 (3-stage pipeline)
7. tests/test_knowledge_rag.py
8. Update __init__.py files         (re-exports)
9. Update pipeline.py               (_rag_node)
10. Update facade.py                (wire all)
11. narrative.py                    (add V3 prompt)
12. day4_verify.py                  (end-to-end)
13. Run full test suite             (target: 130+ tests)
14. Nebius swap                     (after credentials arrive)
```

---

## Key gotchas for next session

| Gotcha | Detail |
|--------|--------|
| ChromaDB shared state in tests | Always use `uuid`-suffixed collection names in test helpers |
| `enrich_poi` region lookup | Must call `_in_region_via_city()` not `_first_neighbor(..., "IN_REGION_VIA_CITY")` |
| `_rag_node` receives preferences | Must read `state.get("preferences")` — already in PipelineState |
| `route_coords` source | `state["route_result"].route_coords` — RouteResult dataclass field |
| Chunk ID format | `"{osm_id}_chunk_{i}"` — POIChunker.get_parent_osm_id() strips `_chunk_{i}` suffix |
| KnowledgeRAG on-route check | Knowledge graph POIs use `kg_` prefix, OSM POIs use OSM IDs — handle both |

---

## What stays the same

- Road network graph (OSMnx, A*, DetourScorer, POISelector) — untouched
- WikipediaFetcher — untouched
- LangGraph pipeline structure — only `_rag_node` body changes
- All 101 existing tests — must stay green
