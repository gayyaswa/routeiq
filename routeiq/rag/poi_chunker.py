"""Splits POI Wikipedia descriptions into chunks and indexes them (mirrors Chunk-PART_OF-Candidate)."""
from __future__ import annotations
from langchain_text_splitters import RecursiveCharacterTextSplitter
from routeiq.graph.poi import POI
from routeiq.rag.poi_indexer import POIIndexer

_CHUNK_SIZE    = 250
_CHUNK_OVERLAP = 20


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

    @staticmethod
    def get_parent_osm_id(chunk_id: str) -> str:
        """Extracts parent POI osm_id from a chunk id like 'kg_alamo_chunk_0'."""
        return chunk_id.rsplit("_chunk_", 1)[0]
