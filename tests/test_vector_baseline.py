"""Unit tests for VectorBaseline — uses in-memory ChromaDB."""
import uuid

import chromadb
import pytest

from routeiq.graph.poi import POI
from routeiq.rag.poi_indexer import POIIndexer
from routeiq.rag.vector_baseline import VectorBaseline


def _setup(pois=None):
    client = chromadb.EphemeralClient()
    indexer = POIIndexer(client=client, collection_name=f"test_{uuid.uuid4().hex}")
    if pois:
        indexer.index(pois)
    baseline = VectorBaseline(indexer)
    return baseline


def _make_poi(osm_id, name, category, description):
    return POI(name=name, category=category, lat=29.0, lon=-98.0, osm_id=osm_id, description=description)


class TestQuery:
    def test_returns_empty_list_when_collection_empty(self):
        baseline = _setup()
        results = baseline.query("historic missions Texas")
        assert results == []

    def test_returns_results_for_indexed_pois(self):
        pois = [
            _make_poi("r1", "Alamo", "historic", "The Alamo is a historic Spanish mission in San Antonio."),
            _make_poi("r2", "Enchanted Rock", "natural", "A giant pink granite dome in the Texas Hill Country."),
        ]
        baseline = _setup(pois)
        results = baseline.query("historic mission")
        assert len(results) >= 1
        assert all("name" in r for r in results)
        assert all("similarity_score" in r for r in results)

    def test_n_results_respects_cap(self):
        pois = [_make_poi(f"r{i}", f"POI {i}", "tourism", f"Description {i}") for i in range(5)]
        baseline = _setup(pois)
        results = baseline.query("scenic landmark", n_results=3)
        assert len(results) <= 3

    def test_n_results_capped_at_collection_size(self):
        pois = [_make_poi("r1", "Only POI", "natural", "A lone natural landmark.")]
        baseline = _setup(pois)
        results = baseline.query("landmark", n_results=10)
        assert len(results) == 1

    def test_result_has_required_keys(self):
        pois = [_make_poi("r1", "Alamo", "historic", "Historic mission.")]
        baseline = _setup(pois)
        results = baseline.query("mission")
        assert len(results) == 1
        r = results[0]
        assert "name" in r
        assert "category" in r
        assert "description" in r
        assert "similarity_score" in r
        assert 0.0 <= r["similarity_score"] <= 1.0
