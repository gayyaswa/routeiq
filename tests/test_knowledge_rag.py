"""Tests for KnowledgeRAG — 3-stage pipeline: vector search, graph filter+augment, context build."""
import uuid
import pytest
import chromadb

from routeiq.graph.poi import POI
from routeiq.graph.knowledge_graph import RouteKnowledgeGraph
from routeiq.rag.poi_indexer import POIIndexer
from routeiq.rag.poi_chunker import POIChunker
from routeiq.rag.knowledge_rag import KnowledgeRAG

# Anchor osm_ids — always present in the Bay Area KG (from knowledge_graph_data anchors)
_COIT = "('way', 28824850)"      # Coit Tower — historic, San Francisco
_FORT = "('relation', 5504536)"  # Fort Point — historic, San Francisco

# SF → Sausalito route coords
_SF_SAUSALITO_COORDS = [(37.7749, -122.4194), (37.8106, -122.4771), (37.8590, -122.4852)]


def _make_indexer() -> POIIndexer:
    client = chromadb.EphemeralClient()
    return POIIndexer(client=client, collection_name=f"test_krag_{uuid.uuid4().hex}")


def _seed_chunks(indexer: POIIndexer) -> None:
    """Index Wikipedia-style descriptions for Bay Area anchors so Stage 1 has content."""
    chunker = POIChunker(indexer)
    pois = [
        POI(
            osm_id=_COIT, name="Coit Tower", category="historic",
            lat=37.8024, lon=-122.4058,
            description=(
                "Coit Tower is a 210-foot tower in the Telegraph Hill neighborhood of San "
                "Francisco, California. Built in 1933, it offers panoramic views of the city "
                "and bay. The tower's interior features Depression-era murals."
            ),
        ),
        POI(
            osm_id=_FORT, name="Fort Point", category="historic",
            lat=37.8106, lon=-122.4771,
            description=(
                "Fort Point National Historic Site is a brick Civil War-era fort located "
                "beneath the Golden Gate Bridge in San Francisco. Built between 1853 and 1861, "
                "it is the only brick fort west of the Mississippi River."
            ),
        ),
    ]
    chunker.chunk_and_index(pois)


@pytest.fixture(scope="module")
def kg():
    return RouteKnowledgeGraph()


def test_stage1_returns_ranked_candidates(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer)
    rag = KnowledgeRAG(indexer, kg)
    candidates = rag._stage1_vector_search(["historic fort San Francisco"], n=5)
    assert len(candidates) > 0
    scores = [c["score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_stage2_filters_out_of_route_pois(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer)
    rag = KnowledgeRAG(indexer, kg)
    # Tiny bbox in Texas — no SF POIs should pass the filter
    tiny_coords = [(29.0, -98.0), (29.1, -98.1)]
    candidates = rag._stage1_vector_search(["historic"], n=5)
    enriched = rag._stage2_filter_augment(candidates, tiny_coords)
    assert enriched == []


def test_stage2_augments_with_city_and_region(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer)
    rag = KnowledgeRAG(indexer, kg)
    candidates = rag._stage1_vector_search(["historic fort"], n=5)
    enriched = rag._stage2_filter_augment(candidates, _SF_SAUSALITO_COORDS)
    assert len(enriched) > 0
    for item in enriched:
        assert item.get("city") is not None
        assert item.get("region") is not None


def test_stage3_context_contains_name_category_region(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer)
    rag = KnowledgeRAG(indexer, kg)
    candidates = rag._stage1_vector_search(["historic fort"], n=5)
    enriched = rag._stage2_filter_augment(candidates, _SF_SAUSALITO_COORDS)
    context = rag._stage3_build_context(enriched)
    assert "historic" in context.lower()
    assert "San Francisco" in context


def test_empty_collection_returns_empty_string(kg):
    indexer = _make_indexer()
    rag = KnowledgeRAG(indexer, kg)
    result = rag.query(["historic"], _SF_SAUSALITO_COORDS)
    assert result == ""


def test_no_route_coords_returns_all_candidates(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer)
    rag = KnowledgeRAG(indexer, kg)
    result = rag.query(["historic fort"], route_coords=[])
    assert result != ""
