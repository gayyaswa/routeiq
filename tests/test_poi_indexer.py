"""Unit tests for POIIndexer — uses in-memory ChromaDB EphemeralClient."""
import uuid

import chromadb
import pytest

from routeiq.graph.poi import POI
from routeiq.rag.poi_indexer import POIIndexer


def _ephemeral_indexer():
    # unique collection name per call prevents state leaking across tests
    client = chromadb.EphemeralClient()
    return POIIndexer(client=client, collection_name=f"test_{uuid.uuid4().hex}")


def _make_poi(osm_id="r1", name="Alamo", category="historic", description=None, image_url=None):
    return POI(
        name=name,
        category=category,
        lat=29.42,
        lon=-98.48,
        osm_id=osm_id,
        description=description,
        image_url=image_url,
    )


class TestIndex:
    def test_indexes_poi_with_description(self):
        indexer = _ephemeral_indexer()
        poi = _make_poi(description="The Alamo is a historic mission in San Antonio.")
        count = indexer.index([poi])
        assert count == 1
        assert indexer.collection.count() == 1

    def test_skips_poi_without_description(self):
        indexer = _ephemeral_indexer()
        poi = _make_poi(description=None)
        count = indexer.index([poi])
        assert count == 0
        assert indexer.collection.count() == 0

    def test_indexes_only_pois_with_descriptions(self):
        indexer = _ephemeral_indexer()
        pois = [
            _make_poi("r1", description="Description one"),
            _make_poi("r2", description=None),
            _make_poi("r3", description="Description three"),
        ]
        count = indexer.index(pois)
        assert count == 2
        assert indexer.collection.count() == 2

    def test_upsert_is_idempotent(self):
        indexer = _ephemeral_indexer()
        poi = _make_poi(description="Some text")
        indexer.index([poi])
        indexer.index([poi])  # upsert same ID
        assert indexer.collection.count() == 1

    def test_metadata_stored_with_image_url(self):
        indexer = _ephemeral_indexer()
        poi = _make_poi(description="Desc", image_url="https://img.example.com/alamo.jpg")
        indexer.index([poi])
        result = indexer.collection.get(ids=["r1"], include=["metadatas"])
        assert result["metadatas"][0]["image_url"] == "https://img.example.com/alamo.jpg"

    def test_metadata_image_url_empty_string_when_none(self):
        indexer = _ephemeral_indexer()
        poi = _make_poi(description="Desc", image_url=None)
        indexer.index([poi])
        result = indexer.collection.get(ids=["r1"], include=["metadatas"])
        assert result["metadatas"][0]["image_url"] == ""

    def test_empty_list_returns_zero(self):
        indexer = _ephemeral_indexer()
        assert indexer.index([]) == 0

    def test_clear_resets_collection(self):
        indexer = _ephemeral_indexer()
        indexer.index([_make_poi(description="text")])
        assert indexer.collection.count() == 1
        indexer.clear()
        assert indexer.collection.count() == 0
