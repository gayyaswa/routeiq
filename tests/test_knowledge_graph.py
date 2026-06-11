"""Tests for RouteKnowledgeGraph — node counts, typed edges, enrichment, route filtering."""
import pytest
from routeiq.graph.knowledge_graph import RouteKnowledgeGraph

# Anchor osm_ids — present whether master cache exists or not
_GGB    = "('way', 370672707)"     # Golden Gate Bridge — tourism, San Francisco
_FORT   = "('relation', 5504536)"  # Fort Point — historic, San Francisco (~1.1 km from GGB)
_COIT   = "('way', 28824850)"      # Coit Tower — historic, San Francisco
_PALACE = "('way', 288371295)"     # Palace of Fine Arts — tourism, San Francisco


@pytest.fixture(scope="module")
def kg():
    return RouteKnowledgeGraph()


def test_node_count_exceeds_20(kg):
    assert kg.node_count() > 20


def test_poi_has_located_in_city(kg):
    # Coit Tower (37.80, -122.41) is clearly nearest to San Francisco
    g = kg.graph
    assert g.has_edge(_COIT, "San Francisco")
    assert g.edges[_COIT, "San Francisco"]["rel"] == "LOCATED_IN"


def test_poi_has_category(kg):
    g = kg.graph
    assert g.has_edge(_COIT, "historic")
    assert g.edges[_COIT, "historic"]["rel"] == "HAS_CATEGORY"


def test_city_has_in_region(kg):
    g = kg.graph
    assert g.has_edge("San Francisco", "San Francisco")
    assert g.edges["San Francisco", "San Francisco"]["rel"] == "IN_REGION"


def test_near_poi_edges_created(kg):
    # Fort Point and Golden Gate Bridge are ~1.1 km apart — well within 25 km
    g = kg.graph
    assert g.has_edge(_FORT, _GGB)
    assert g.edges[_FORT, _GGB]["rel"] == "NEAR_POI"
    assert g.has_edge(_GGB, _FORT)


def test_enrich_poi_returns_city_region_category(kg):
    result = kg.enrich_poi(_COIT)
    assert result["city"] == "San Francisco"
    assert result["region"] == "San Francisco"
    assert result["category"] == "historic"
    assert isinstance(result["nearby_pois"], list)


def test_get_pois_for_route_sf_sausalito(kg):
    # Route coords: SF → Golden Gate → Sausalito
    route_coords = [(37.7749, -122.4194), (37.8106, -122.4771), (37.8590, -122.4852)]
    poi_ids = kg.get_pois_for_route(route_coords)
    # San Francisco POIs should be on this route (GGB, Fort Point, Coit Tower all in SF)
    assert _GGB in poi_ids
    assert _FORT in poi_ids
    assert _COIT in poi_ids


def test_get_pois_for_route_empty_coords_returns_empty(kg):
    assert kg.get_pois_for_route([]) == []
