"""NetworkX knowledge graph: POI/City/Region/Category nodes with typed edges (Registry pattern)."""
from __future__ import annotations
import dataclasses
import math
from typing import Any
import networkx as nx
from routeiq.graph.knowledge_graph_data import POIS, CITIES, REGIONS, CATEGORIES, RELATIONSHIPS
from routeiq.graph.poi import POI

_POI_FIELDS = {f.name for f in dataclasses.fields(POI)}


class RouteKnowledgeGraph:
    """Builds and queries a knowledge graph of Texas scenic route entities (Registry pattern).

    Node types: POI, City, Region, Category
    Edge types: LOCATED_IN, HAS_CATEGORY, IN_REGION, NEAR_POI
    """

    _NEAR_POI_MAX_KM = 25.0

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()
        self._build()

    @property
    def graph(self) -> nx.DiGraph:
        return self._g

    def enrich_poi(self, osm_id: str) -> dict:
        """Returns {city, region, category, nearby_poi_names} for a POI node."""
        if osm_id not in self._g:
            return {}
        city = self._first_neighbor(osm_id, "LOCATED_IN")
        region = self._in_region_via_city(osm_id)
        category = self._first_neighbor(osm_id, "HAS_CATEGORY")
        nearby = [
            self._g.nodes[n]["name"]
            for n in self._g.successors(osm_id)
            if self._g.edges[osm_id, n].get("rel") == "NEAR_POI"
        ]
        return {"city": city, "region": region, "category": category, "nearby_pois": nearby}

    def get_pois_for_route(self, route_coords: list[tuple[float, float]]) -> list[str]:
        """Returns osm_ids of POIs whose city falls within the route bounding box (+0.3 deg pad)."""
        if not route_coords:
            return []
        lats = [c[0] for c in route_coords]
        lons = [c[1] for c in route_coords]
        pad = 0.3
        north, south = max(lats) + pad, min(lats) - pad
        east, west   = max(lons) + pad, min(lons) - pad

        on_route_cities = {
            n for n, d in self._g.nodes(data=True)
            if d.get("type") == "City"
            and south <= d["lat"] <= north
            and west  <= d["lon"] <= east
        }
        return [
            n for n, d in self._g.nodes(data=True)
            if d.get("type") == "POI"
            and self._city_for_poi(n) in on_route_cities
        ]

    def get_all_pois(self) -> list[str]:
        """Returns all POI osm_ids in the graph."""
        return [n for n, d in self._g.nodes(data=True) if d.get("type") == "POI"]

    def known_cities(self) -> set[str]:
        """Returns the set of city names currently in the graph."""
        return {d["name"] for n, d in self._g.nodes(data=True) if d.get("type") == "City"}

    def get_pois_for_city(self, city_name: str) -> list[POI]:
        """Return POIs spatially contained within city_name's OSM administrative boundary.

        Uses geocode_to_gdf to fetch the real city polygon from OSM (cached per instance),
        so correctness does not depend on the _nearest_city heuristic used when building
        LOCATED_IN edges.  The LOCATED_IN pre-filter still runs as a fast coarse pass to
        avoid polygon-checking every POI in the graph.
        """
        from shapely.geometry import Point
        short = city_name.split(",")[0].strip()
        city_poly = self._city_polygon(city_name)

        result = []
        for node_id, data in self._g.nodes(data=True):
            if data.get("type") != "POI":
                continue
            poi = POI(**{k: v for k, v in data.items() if k in _POI_FIELDS})
            if city_poly is not None:
                # Polygon is authoritative — supersedes LOCATED_IN heuristic so
                # border attractions (e.g. Golden Gate Bridge → Sausalito) are included.
                if not city_poly.contains(Point(poi.lon, poi.lat)):
                    continue
            else:
                # No polygon available — fall back to LOCATED_IN heuristic.
                poi_city = self._city_for_poi(node_id)
                if poi_city is not None and poi_city != short:
                    continue
            result.append(poi)
        return result

    def _city_polygon(self, city_name: str):
        """Fetch and cache the OSM administrative boundary polygon for city_name."""
        if not hasattr(self, "_poly_cache"):
            self._poly_cache: dict = {}
        if city_name not in self._poly_cache:
            try:
                import osmnx as ox
                gdf = ox.geocoder.geocode_to_gdf(city_name)
                self._poly_cache[city_name] = gdf.geometry.iloc[0]
                print(f"[kg] polygon fetched for '{city_name}'", flush=True)
            except Exception as exc:
                print(f"[kg] polygon fetch failed for '{city_name}': {exc} — falling back to LOCATED_IN only", flush=True)
                self._poly_cache[city_name] = None
        return self._poly_cache[city_name]

    def add_city_pois(
        self,
        city_name: str,
        city_lat: float,
        city_lon: float,
        pois: list[POI],
    ) -> None:
        """Add a new city node + its POIs to the in-memory graph.

        Safe to call multiple times for the same city — existing nodes are not duplicated.
        """
        if city_name not in self._g:
            self._g.add_node(city_name, type="City", name=city_name, lat=city_lat, lon=city_lon)
        for poi in pois:
            if poi.osm_id not in self._g:
                self._g.add_node(poi.osm_id, type="POI", **dataclasses.asdict(poi))
                self._g.add_edge(poi.osm_id, city_name, rel="LOCATED_IN")
        self._add_near_poi_edges_for(pois)

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    # ── private ────────────────────────────────────────────────────────────

    def _build(self) -> None:
        for cat in CATEGORIES:
            self._g.add_node(cat["name"], type="Category", name=cat["name"])
        for reg in REGIONS:
            self._g.add_node(reg["name"], type="Region", name=reg["name"])
        for city in CITIES:
            self._g.add_node(city["name"], type="City", **city)
        for poi in POIS:
            self._g.add_node(poi["osm_id"], type="POI", **poi)
        for src, rel, tgt in RELATIONSHIPS:
            self._g.add_edge(src, tgt, rel=rel)
        self._add_near_poi_edges()

    def _add_near_poi_edges(self) -> None:
        poi_nodes = [(n, d) for n, d in self._g.nodes(data=True) if d.get("type") == "POI"]
        for i, (id_a, d_a) in enumerate(poi_nodes):
            for id_b, d_b in poi_nodes[i + 1:]:
                dist = self._haversine(d_a["lat"], d_a["lon"], d_b["lat"], d_b["lon"])
                if dist <= self._NEAR_POI_MAX_KM:
                    self._g.add_edge(id_a, id_b, rel="NEAR_POI", dist_km=round(dist, 1))
                    self._g.add_edge(id_b, id_a, rel="NEAR_POI", dist_km=round(dist, 1))

    def _add_near_poi_edges_for(self, pois: list[POI]) -> None:
        """Compute NEAR_POI edges only among the supplied POIs (used for dynamic city additions)."""
        for i, poi_a in enumerate(pois):
            for poi_b in pois[i + 1:]:
                dist = self._haversine(poi_a.lat, poi_a.lon, poi_b.lat, poi_b.lon)
                if dist <= self._NEAR_POI_MAX_KM:
                    self._g.add_edge(poi_a.osm_id, poi_b.osm_id, rel="NEAR_POI", dist_km=round(dist, 1))
                    self._g.add_edge(poi_b.osm_id, poi_a.osm_id, rel="NEAR_POI", dist_km=round(dist, 1))

    def _city_for_poi(self, osm_id: str) -> str | None:
        return self._first_neighbor(osm_id, "LOCATED_IN")

    def _first_neighbor(self, node_id: str, rel: str) -> str | None:
        for nbr in self._g.successors(node_id):
            if self._g.edges[node_id, nbr].get("rel") == rel:
                return self._g.nodes[nbr].get("name", nbr)
        return None

    def _in_region_via_city(self, osm_id: str) -> str | None:
        city = self._city_for_poi(osm_id)
        if not city:
            return None
        for nbr in self._g.successors(city):
            if self._g.edges[city, nbr].get("rel") == "IN_REGION":
                return self._g.nodes[nbr].get("name", nbr)
        return None

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
