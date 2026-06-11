"""Pure semantic retrieval baseline — no graph constraints (Strategy pattern)."""
from __future__ import annotations

from routeiq.rag.poi_indexer import POIIndexer


class VectorBaseline:
    """Retrieves POIs by semantic similarity only, ignoring graph routing (Strategy pattern).

    Used in Day 4 evaluation: GraphRAG results vs. this vector-only baseline.
    """

    def __init__(self, indexer: POIIndexer) -> None:
        self._collection = indexer.collection

    def query(self, text: str, n_results: int = 5) -> list[dict]:
        """Returns top-N POIs ranked by semantic similarity to the query text.

        Each result dict has keys: name, category, description, similarity_score.
        similarity_score is 1 - cosine_distance (higher = more similar).
        """
        count = self._collection.count()
        if count == 0:
            return []
        k = min(n_results, count)
        results = self._collection.query(
            query_texts=[text],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "name": meta["name"],
                "category": meta["category"],
                "description": doc,
                "similarity_score": round(1.0 - dist, 4),
                "image_url": meta.get("image_url") or None,
            }
            for meta, doc, dist in zip(
                results["metadatas"][0],
                results["documents"][0],
                results["distances"][0],
            )
        ]
