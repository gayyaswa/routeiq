"""Unit tests for POIRetriever — uses in-memory ChromaDB."""
import uuid

import chromadb
import pytest

from routeiq.graph.poi import POI
from routeiq.rag.poi_indexer import POIIndexer
from routeiq.rag.poi_retriever import POIRetriever


def _setup(pois=None):
    client = chromadb.EphemeralClient()
    indexer = POIIndexer(client=client, collection_name=f"test_{uuid.uuid4().hex}")
    if pois:
        indexer.index(pois)
    retriever = POIRetriever(indexer)
    return retriever


def _make_poi(osm_id, name, description):
    return POI(name=name, category="historic", lat=29.0, lon=-98.0, osm_id=osm_id, description=description)


class TestGetContext:
    def test_returns_description_for_indexed_poi(self):
        poi = _make_poi("r1", "Alamo", "The Alamo mission in San Antonio.")
        retriever = _setup([poi])
        ctx = retriever.get_context(["r1"])
        assert ctx == {"r1": "The Alamo mission in San Antonio."}

    def test_multiple_ids_returned(self):
        pois = [
            _make_poi("r1", "Alamo", "Alamo description."),
            _make_poi("r2", "Mission", "Mission description."),
        ]
        retriever = _setup(pois)
        ctx = retriever.get_context(["r1", "r2"])
        assert len(ctx) == 2
        assert "Alamo description." in ctx.values()

    def test_unknown_id_omitted(self):
        poi = _make_poi("r1", "Alamo", "Alamo description.")
        retriever = _setup([poi])
        ctx = retriever.get_context(["r1", "unknown_id"])
        # ChromaDB raises on unknown IDs, but our implementation returns {}
        # when an exception occurs — or returns only found IDs
        assert "r1" in ctx

    def test_empty_ids_returns_empty_dict(self):
        retriever = _setup()
        ctx = retriever.get_context([])
        assert ctx == {}
