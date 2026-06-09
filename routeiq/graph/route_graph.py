from __future__ import annotations
import osmnx as ox
import networkx as nx
from routeiq.graph.route_result import RouteResult


class RouteGraph:
    """Finds shortest paths on an OSM road network using A* with haversine heuristic (Strategy pattern)."""

    def __init__(self, graph: nx.MultiDiGraph, avg_speed_kmh: float = 50.0):
        self._graph = graph
        self._avg_speed_kmh = avg_speed_kmh

    def find_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> RouteResult:
        orig = ox.distance.nearest_nodes(self._graph, X=origin_lon, Y=origin_lat)
        dest = ox.distance.nearest_nodes(self._graph, X=dest_lon, Y=dest_lat)

        try:
            route_nodes = nx.astar_path(
                self._graph,
                orig,
                dest,
                heuristic=self._haversine_heuristic,
                weight="length",
            )
        except nx.NetworkXNoPath:
            raise ValueError(
                f"No path found from ({origin_lat}, {origin_lon}) to ({dest_lat}, {dest_lon})"
            )

        length_m = nx.path_weight(self._graph, route_nodes, weight="length")
        length_km = length_m / 1000.0
        drive_time_min = (length_km / self._avg_speed_kmh) * 60.0
        route_coords = [
            (self._graph.nodes[n]["y"], self._graph.nodes[n]["x"]) for n in route_nodes
        ]

        return RouteResult(
            route_nodes=route_nodes,
            route_coords=route_coords,
            length_km=length_km,
            drive_time_min=drive_time_min,
        )

    def _haversine_heuristic(self, u: int, v: int) -> float:
        return ox.distance.great_circle(
            lat1=self._graph.nodes[u]["y"],
            lon1=self._graph.nodes[u]["x"],
            lat2=self._graph.nodes[v]["y"],
            lon2=self._graph.nodes[v]["x"],
        )
