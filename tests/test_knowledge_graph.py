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


# ── new methods: known_cities / get_pois_for_city / add_city_pois ──────────

def test_known_cities_contains_sf(kg):
    assert "San Francisco" in kg.known_cities()


def test_known_cities_returns_set(kg):
    cities = kg.known_cities()
    assert isinstance(cities, set)
    assert len(cities) >= 10   # at least the 10 Bay Area cities


def test_get_pois_for_city_sf_returns_pois(kg):
    pois = kg.get_pois_for_city("San Francisco")
    names = [p.name for p in pois]
    assert "Coit Tower" in names
    # Golden Gate Bridge LOCATED_IN = Sausalito (heuristic), but its coordinates
    # are inside SF's OSM polygon — polygon gate overrides LOCATED_IN.
    assert "Golden Gate Bridge" in names


def test_get_pois_for_city_strips_state_suffix(kg):
    # "San Francisco, CA" should match "San Francisco"
    pois_full = kg.get_pois_for_city("San Francisco, CA")
    pois_short = kg.get_pois_for_city("San Francisco")
    assert len(pois_full) == len(pois_short)


def test_get_pois_for_city_unknown_city_returns_empty(kg):
    assert kg.get_pois_for_city("Atlantis, ZZ") == []


def test_add_city_pois_adds_city_node():
    from routeiq.graph.poi import POI
    kg2 = RouteKnowledgeGraph()
    assert "Los Angeles" not in kg2.known_cities()

    new_pois = [
        POI(name="Getty Center", category="tourism", lat=34.0780, lon=-118.4741, osm_id="way/la_001"),
        POI(name="Griffith Park", category="natural", lat=34.1366, lon=-118.2940, osm_id="way/la_002"),
    ]
    kg2.add_city_pois("Los Angeles", 34.05, -118.24, new_pois)

    assert "Los Angeles" in kg2.known_cities()
    pois = kg2.get_pois_for_city("Los Angeles")
    assert len(pois) == 2
    assert {p.name for p in pois} == {"Getty Center", "Griffith Park"}


def test_add_city_pois_creates_near_poi_edges():
    from routeiq.graph.poi import POI
    kg2 = RouteKnowledgeGraph()
    # Two POIs ~7 km apart — within NEAR_POI_MAX_KM (25 km)
    new_pois = [
        POI(name="Getty Center", category="tourism", lat=34.0780, lon=-118.4741, osm_id="way/la_001"),
        POI(name="Griffith Park", category="natural", lat=34.1366, lon=-118.2940, osm_id="way/la_002"),
    ]
    kg2.add_city_pois("Los Angeles", 34.05, -118.24, new_pois)

    g = kg2.graph
    assert g.has_edge("way/la_001", "way/la_002")
    assert g.edges["way/la_001", "way/la_002"]["rel"] == "NEAR_POI"


def test_add_city_pois_idempotent():
    from routeiq.graph.poi import POI
    kg2 = RouteKnowledgeGraph()
    poi = POI(name="Getty Center", category="tourism", lat=34.0780, lon=-118.4741, osm_id="way/la_001")
    kg2.add_city_pois("Los Angeles", 34.05, -118.24, [poi])
    kg2.add_city_pois("Los Angeles", 34.05, -118.24, [poi])   # second call — no duplicates
    assert len(kg2.get_pois_for_city("Los Angeles")) == 1
