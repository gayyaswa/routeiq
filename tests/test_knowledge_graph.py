"""Tests for RouteKnowledgeGraph — node counts, typed edges, enrichment, route filtering."""
import pytest
from routeiq.graph.knowledge_graph import RouteKnowledgeGraph


@pytest.fixture(scope="module")
def kg():
    return RouteKnowledgeGraph()


def test_node_count_exceeds_20(kg):
    assert kg.node_count() > 20


def test_poi_has_located_in_city(kg):
    g = kg.graph
    assert g.has_edge("kg_alamo", "San Antonio")
    assert g.edges["kg_alamo", "San Antonio"]["rel"] == "LOCATED_IN"


def test_poi_has_category(kg):
    g = kg.graph
    assert g.has_edge("kg_alamo", "mission")
    assert g.edges["kg_alamo", "mission"]["rel"] == "HAS_CATEGORY"


def test_city_has_in_region(kg):
    g = kg.graph
    assert g.has_edge("San Antonio", "San Antonio Missions")
    assert g.edges["San Antonio", "San Antonio Missions"]["rel"] == "IN_REGION"


def test_near_poi_edges_created(kg):
    # The Alamo and Mission Concepción are ~2.4 km apart — well within 25 km
    g = kg.graph
    assert g.has_edge("kg_alamo", "kg_concepcion")
    assert g.edges["kg_alamo", "kg_concepcion"]["rel"] == "NEAR_POI"
    # Edge is bidirectional
    assert g.has_edge("kg_concepcion", "kg_alamo")


def test_enrich_poi_returns_city_region_category(kg):
    result = kg.enrich_poi("kg_alamo")
    assert result["city"] == "San Antonio"
    assert result["region"] == "San Antonio Missions"
    assert result["category"] == "mission"
    assert isinstance(result["nearby_pois"], list)


def test_get_pois_for_route_austin_sa(kg):
    # Route coords spanning Austin (30.27, -97.74) → San Antonio (29.42, -98.49)
    route_coords = [(30.27, -97.74), (29.70, -98.10), (29.42, -98.49)]
    poi_ids = kg.get_pois_for_route(route_coords)
    # San Antonio POIs should be on this route
    assert "kg_alamo" in poi_ids
    assert "kg_national_museum" in poi_ids


def test_get_pois_for_route_empty_coords_returns_empty(kg):
    assert kg.get_pois_for_route([]) == []
