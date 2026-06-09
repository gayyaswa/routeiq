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
        candidates = self._stage1_vector_search(preferences, n_candidates)
        if not candidates:
            return ""
        enriched = self._stage2_filter_augment(candidates, route_coords)
        if not enriched:
            return ""
        return self._stage3_build_context(enriched)

    def _stage1_vector_search(self, preferences: list[str], n: int) -> list[dict]:
        """Embed preferences → query ChromaDB chunks → return ranked (parent_osm_id, score, evidence)."""
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
        """Filter by on-route bounding box, augment each candidate with knowledge graph data."""
        no_route_specified = not route_coords
        on_route_ids = set(self._kg.get_pois_for_route(route_coords))
        enriched = []
        for candidate in candidates:
            osm_id = candidate["osm_id"]
            is_on_route = (
                osm_id in on_route_ids
                or any(r.startswith(osm_id) or osm_id.startswith(r) for r in on_route_ids)
            )
            # Skip when a route is specified but this POI's city is not in the bbox
            if not no_route_specified and not is_on_route:
                continue
            graph_data = self._kg.enrich_poi(osm_id)
            enriched.append({**candidate, **graph_data})
        return enriched

    def _stage3_build_context(self, enriched: list[dict]) -> str:
        """Format enriched POI data as a context string for Claude (Stage 3)."""
        lines = []
        for item in enriched:
            nearby = ", ".join(item.get("nearby_pois", [])[:3]) or "none"
            lines.append(
                f"{item['name']} | {item.get('category', '?')} | "
                f"{item.get('city', '?')} | {item.get('region', '?')} | "
                f"nearby: {nearby} | {item['evidence']}"
            )
        return "\n\n".join(lines)
