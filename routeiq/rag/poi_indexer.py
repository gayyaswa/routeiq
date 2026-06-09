"""Indexes enriched POI documents in ChromaDB for semantic retrieval (Registry pattern)."""
from __future__ import annotations

import chromadb

from routeiq.graph.poi import POI

_DEFAULT_COLLECTION = "routeiq_pois"


class POIIndexer:
    """Writes enriched POI documents to a ChromaDB collection (Registry pattern)."""

    def __init__(
        self,
        client: chromadb.ClientAPI | None = None,
        persist_dir: str = "./cache/chroma",
        collection_name: str = _DEFAULT_COLLECTION,
    ) -> None:
        self._client = client or chromadb.PersistentClient(path=persist_dir)
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(collection_name)

    @property
    def collection(self) -> chromadb.Collection:
        return self._collection

    def index(self, pois: list[POI]) -> int:
        """Upsert POIs that have descriptions; returns count of indexed documents."""
        enriched = [p for p in pois if p.description]
        if not enriched:
            return 0
        self._collection.upsert(
            ids=[p.osm_id for p in enriched],
            documents=[p.description for p in enriched],
            metadatas=[
                {
                    "name": p.name,
                    "category": p.category,
                    "lat": p.lat,
                    "lon": p.lon,
                    "image_url": p.image_url or "",
                }
                for p in enriched
            ],
        )
        return len(enriched)

    def clear(self) -> None:
        """Drop and recreate the collection (useful between pipeline runs)."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(self._collection_name)
