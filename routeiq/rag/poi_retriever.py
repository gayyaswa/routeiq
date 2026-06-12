"""Retrieves POI descriptions from ChromaDB by OSM ID (Facade pattern)."""
from __future__ import annotations

from routeiq.rag.poi_indexer import POIIndexer


class POIRetriever:
    """Reads POI context from ChromaDB by OSM ID for narrative enrichment (Facade pattern)."""

    def __init__(self, indexer: POIIndexer) -> None:
        self._collection = indexer.collection

    def get_context(self, osm_ids: list[str]) -> dict[str, str]:
        """Returns {osm_id: description} for the given IDs; missing IDs are omitted."""
        if not osm_ids:
            return {}
        try:
            result = self._collection.get(ids=osm_ids, include=["documents"])
            return {id_: doc for id_, doc in zip(result["ids"], result["documents"]) if doc}
        except Exception:
            return {}
