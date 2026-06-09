import math
from unittest.mock import patch

import networkx as nx
import pytest

from routeiq.graph import RouteGraph, RouteResult


def _build_graph() -> nx.MultiDiGraph:
    """Linear 5-node graph: 0→1→2→3→4, plus isolated node 5."""
    G = nx.MultiDiGraph()
    coords = [
        (0, -98.0, 29.50),
        (1, -97.9, 29.52),
        (2, -97.8, 29.54),
        (3, -97.7, 29.55),
        (4, -97.6, 29.56),
        (5, -97.5, 29.00),  # isolated — no path to node 4
    ]
    for node_id, lon, lat in coords:
        G.add_node(node_id, x=lon, y=lat)
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 4)]:
        G.add_edge(u, v, length=1000)
    return G


@pytest.fixture
def rg():
    return RouteGraph(_build_graph(), avg_speed_kmh=50.0)


class TestRouteGraphFindRoute:
    def test_returns_route_result(self, rg):
        with patch("osmnx.distance.nearest_nodes", side_effect=[0, 4]):
            result = rg.find_route(29.50, -98.0, 29.56, -97.6)
        assert isinstance(result, RouteResult)

    def test_first_node_is_origin_last_is_destination(self, rg):
        with patch("osmnx.distance.nearest_nodes", side_effect=[0, 4]):
            result = rg.find_route(29.50, -98.0, 29.56, -97.6)
        assert result.route_nodes[0] == 0
        assert result.route_nodes[-1] == 4

    def test_coords_length_matches_nodes(self, rg):
        with patch("osmnx.distance.nearest_nodes", side_effect=[0, 4]):
            result = rg.find_route(29.50, -98.0, 29.56, -97.6)
        assert len(result.route_coords) == len(result.route_nodes)

    def test_length_km_positive(self, rg):
        with patch("osmnx.distance.nearest_nodes", side_effect=[0, 4]):
            result = rg.find_route(29.50, -98.0, 29.56, -97.6)
        assert result.length_km > 0

    def test_drive_time_derived_from_length(self, rg):
        with patch("osmnx.distance.nearest_nodes", side_effect=[0, 4]):
            result = rg.find_route(29.50, -98.0, 29.56, -97.6)
        expected = (result.length_km / 50.0) * 60.0
        assert math.isclose(result.drive_time_min, expected, rel_tol=1e-9)

    def test_length_km_equals_four_edges(self, rg):
        # 4 edges × 1000 m = 4 km
        with patch("osmnx.distance.nearest_nodes", side_effect=[0, 4]):
            result = rg.find_route(29.50, -98.0, 29.56, -97.6)
        assert math.isclose(result.length_km, 4.0, rel_tol=1e-9)

    def test_disconnected_node_raises_value_error(self, rg):
        with patch("osmnx.distance.nearest_nodes", side_effect=[0, 5]):
            with pytest.raises(ValueError, match="No path found"):
                rg.find_route(29.50, -98.0, 29.00, -97.5)
