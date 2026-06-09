from __future__ import annotations
import pandas as pd
import osmnx as ox
from shapely.geometry import LineString
from routeiq.graph.poi import POI


class POIFinder:
    """Spatially joins OSM features within a buffer around a route (Pipeline pattern)."""

    def __init__(self, buffer_km: float = 5.0):
        self._buffer_km = buffer_km

    def find_pois(self, route_coords: list[tuple[float, float]]) -> list[POI]:
        if not route_coords:
            return []

        line = LineString([(lon, lat) for lat, lon in route_coords])
        buffer_deg = self._buffer_km / 111.0
        buffer_poly = line.buffer(buffer_deg)

        tags = {"tourism": True, "historic": True, "natural": True}
        minx, miny, maxx, maxy = buffer_poly.bounds

        try:
            gdf = ox.features_from_bbox(bbox=(minx, miny, maxx, maxy), tags=tags)
        except Exception:
            return []

        pois: list[POI] = []
        for _, row in gdf.iterrows():
            name = row.get("name")
            if pd.isna(name) or not name:
                continue

            geom = row.geometry
            centroid = geom if geom.geom_type == "Point" else geom.centroid

            if not buffer_poly.contains(centroid):
                continue

            if pd.notna(row.get("historic")):
                category = "historic"
            elif pd.notna(row.get("tourism")):
                category = "tourism"
            elif pd.notna(row.get("natural")):
                category = "natural"
            else:
                continue

            wikipedia_tag = row.get("wikipedia")
            if pd.isna(wikipedia_tag):
                wikipedia_tag = None

            pois.append(
                POI(
                    name=str(name),
                    category=category,
                    lat=centroid.y,
                    lon=centroid.x,
                    osm_id=str(row.name),
                    wikipedia_tag=wikipedia_tag,
                )
            )

        return pois
