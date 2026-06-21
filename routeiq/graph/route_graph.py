from __future__ import annotations
import osmnx as ox
import networkx as nx
from routeiq.graph.route_result import RouteResult


# Fastest road type in OSM (motorway) defaults to 130 km/h = 36.11 m/s.
# Dividing haversine distance by this gives an admissible (never-overestimating)
# travel_time heuristic for A* when weight="travel_time" (seconds).
_MAX_SPEED_MS = 130.0 / 3.6


class RouteGraph:
    """Finds fastest paths on an OSM road network using A* with per-edge travel times (Strategy pattern)."""

    def __init__(self, graph: nx.MultiDiGraph):
        self._graph = graph

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
                weight="travel_time",
            )
        except nx.NetworkXNoPath:
            raise ValueError(
                f"No path found from ({origin_lat}, {origin_lon}) to ({dest_lat}, {dest_lon})"
            )

        length_m = nx.path_weight(self._graph, route_nodes, weight="length")
        travel_time_s = nx.path_weight(self._graph, route_nodes, weight="travel_time")
        route_coords = [
            (self._graph.nodes[n]["y"], self._graph.nodes[n]["x"]) for n in route_nodes
        ]

        return RouteResult(
            route_nodes=route_nodes,
            route_coords=route_coords,
            length_km=length_m / 1000.0,
            drive_time_min=travel_time_s / 60.0,
        )

    def _haversine_heuristic(self, u: int, v: int) -> float:
        # Returns estimated travel time in seconds — consistent with weight="travel_time".
        dist_m = ox.distance.great_circle(
            lat1=self._graph.nodes[u]["y"],
            lon1=self._graph.nodes[u]["x"],
            lat2=self._graph.nodes[v]["y"],
            lon2=self._graph.nodes[v]["x"],
        )
        return dist_m / _MAX_SPEED_MS
