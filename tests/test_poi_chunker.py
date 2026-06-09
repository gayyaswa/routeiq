"""Tests for POIChunker — splitting, chunk size, indexing, and parent ID extraction."""
import uuid
import pytest
import chromadb

from routeiq.graph.poi import POI
from routeiq.rag.poi_indexer import POIIndexer
from routeiq.rag.poi_chunker import POIChunker


def _make_indexer() -> POIIndexer:
    client = chromadb.EphemeralClient()
    return POIIndexer(client=client, collection_name=f"test_chunks_{uuid.uuid4().hex}")


def _make_poi(description: str, osm_id: str = "kg_test") -> POI:
    return POI(
        name="Test POI", category="historic",
        lat=29.4, lon=-98.5, osm_id=osm_id, description=description,
    )


def test_chunks_description_into_parts():
    indexer = _make_indexer()
    chunker = POIChunker(indexer)
    long_desc = "A " * 300  # 600 chars — forces multiple chunks
    poi = _make_poi(long_desc)
    count = chunker.chunk_and_index([poi])
    assert count > 1


def test_chunk_size_respected():
    indexer = _make_indexer()
    chunker = POIChunker(indexer)
    long_desc = "word " * 200  # well over 250 chars
    poi = _make_poi(long_desc)
    chunker.chunk_and_index([poi])
    results = indexer.collection.get(include=["documents"])
    for doc in results["documents"]:
        assert len(doc) <= 270  # allow slight overlap spillover


def test_poi_without_description_skipped():
    indexer = _make_indexer()
    chunker = POIChunker(indexer)
    poi = POI(name="Empty", category="natural", lat=30.0, lon=-98.0, osm_id="kg_empty")
    count = chunker.chunk_and_index([poi])
    assert count == 0
    assert indexer.collection.count() == 0


def test_chunk_id_contains_parent_osm_id():
    indexer = _make_indexer()
    chunker = POIChunker(indexer)
    poi = _make_poi("word " * 200, osm_id="kg_alamo")
    chunker.chunk_and_index([poi])
    ids = indexer.collection.get()["ids"]
    assert all(id_.startswith("kg_alamo_chunk_") for id_ in ids)


def test_get_parent_osm_id_extracts_correctly():
    assert POIChunker.get_parent_osm_id("kg_alamo_chunk_0") == "kg_alamo"
    assert POIChunker.get_parent_osm_id("kg_enchanted_rock_chunk_3") == "kg_enchanted_rock"
    assert POIChunker.get_parent_osm_id("kg_natural_bridge_chunk_0") == "kg_natural_bridge"


def test_indexes_all_chunks_to_chromadb():
    indexer = _make_indexer()
    chunker = POIChunker(indexer)
    pois = [
        _make_poi("The Alamo is a historic mission in San Antonio. " * 10, "kg_alamo"),
        _make_poi("Enchanted Rock is a granite dome in the Hill Country. " * 10, "kg_enchanted_rock"),
    ]
    count = chunker.chunk_and_index(pois)
    assert count >= 2
    assert indexer.collection.count() == count
