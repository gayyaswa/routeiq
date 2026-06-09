"""Tests for KnowledgeRAG — 3-stage pipeline: vector search, graph filter+augment, context build."""
import uuid
import pytest
import chromadb

from routeiq.graph.poi import POI
from routeiq.graph.knowledge_graph import RouteKnowledgeGraph
from routeiq.rag.poi_indexer import POIIndexer
from routeiq.rag.poi_chunker import POIChunker
from routeiq.rag.knowledge_rag import KnowledgeRAG


# Austin → San Antonio route coords
_AUSTIN_SA_COORDS = [(30.27, -97.74), (29.70, -98.10), (29.42, -98.49)]


def _make_indexer() -> POIIndexer:
    client = chromadb.EphemeralClient()
    return POIIndexer(client=client, collection_name=f"test_krag_{uuid.uuid4().hex}")


def _seed_chunks(indexer: POIIndexer, kg: RouteKnowledgeGraph) -> None:
    """Index Wikipedia-style descriptions for SA missions so Stage 1 has content."""
    chunker = POIChunker(indexer)
    pois = [
        POI(
            osm_id="kg_alamo", name="The Alamo", category="mission",
            lat=29.426, lon=-98.486,
            description=(
                "The Alamo is a historic Spanish colonial mission in San Antonio, Texas. "
                "Built in 1718, it was the site of the famous 1836 Battle of the Alamo "
                "during the Texas Revolution. Today it is a UNESCO World Heritage Site."
            ),
        ),
        POI(
            osm_id="kg_concepcion", name="Mission Concepción", category="mission",
            lat=29.406, lon=-98.487,
            description=(
                "Mission Concepción is the oldest unrestored stone church in the United States, "
                "located in San Antonio. Founded in 1731, it features original frescoes and "
                "is part of the San Antonio Missions UNESCO World Heritage Site."
            ),
        ),
    ]
    chunker.chunk_and_index(pois)


@pytest.fixture(scope="module")
def kg():
    return RouteKnowledgeGraph()


def test_stage1_returns_ranked_candidates(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer, kg)
    rag = KnowledgeRAG(indexer, kg)
    candidates = rag._stage1_vector_search(["historic missions", "Texas Revolution"], n=5)
    assert len(candidates) > 0
    # Results should be ranked by score descending
    scores = [c["score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_stage2_filters_out_of_route_pois(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer, kg)
    rag = KnowledgeRAG(indexer, kg)
    # Tiny bbox that can't contain San Antonio (29.42, -98.49)
    tiny_coords = [(35.0, -95.0), (35.1, -95.1)]
    candidates = rag._stage1_vector_search(["historic"], n=5)
    enriched = rag._stage2_filter_augment(candidates, tiny_coords)
    assert enriched == []


def test_stage2_augments_with_city_and_region(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer, kg)
    rag = KnowledgeRAG(indexer, kg)
    candidates = rag._stage1_vector_search(["mission"], n=5)
    enriched = rag._stage2_filter_augment(candidates, _AUSTIN_SA_COORDS)
    assert len(enriched) > 0
    for item in enriched:
        assert item.get("city") is not None
        assert item.get("region") is not None


def test_stage3_context_contains_name_category_region(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer, kg)
    rag = KnowledgeRAG(indexer, kg)
    candidates = rag._stage1_vector_search(["historic mission"], n=5)
    enriched = rag._stage2_filter_augment(candidates, _AUSTIN_SA_COORDS)
    context = rag._stage3_build_context(enriched)
    assert "mission" in context.lower()
    assert "San Antonio" in context
    assert "San Antonio Missions" in context


def test_empty_collection_returns_empty_string(kg):
    indexer = _make_indexer()
    rag = KnowledgeRAG(indexer, kg)
    result = rag.query(["historic"], _AUSTIN_SA_COORDS)
    assert result == ""


def test_no_route_coords_returns_all_candidates(kg):
    indexer = _make_indexer()
    _seed_chunks(indexer, kg)
    rag = KnowledgeRAG(indexer, kg)
    # Empty route_coords → on_route_ids is empty → Stage 2 includes all candidates
    result = rag.query(["mission"], route_coords=[])
    assert result != ""
