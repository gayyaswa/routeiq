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

        # Scenic tourism subtypes only — excludes hotels, hostels, artwork, galleries, campsites
        _SCENIC_TOURISM = [
            "viewpoint", "museum", "attraction", "aquarium", "zoo",
            "theme_park", "lighthouse", "monument",
        ]
        # Explicit historic subtypes with reliable Wikipedia coverage.
        # "historic: True" returned thousands of minor features (roads, fences, districts)
        # whose names don't resolve to Wikipedia articles, breaking enrichment entirely.
        _SCENIC_HISTORIC = [
            "castle", "fort", "monument", "memorial", "ruins",
            "archaeological_site", "lighthouse", "manor", "battlefield",
        ]
        # Natural subtypes worth visiting on a road trip
        _SCENIC_NATURAL = [
            "peak", "volcano", "beach", "cape", "cliff", "waterfall",
            "hot_spring", "cave_entrance", "bay", "glacier", "wood",
        ]
        tags = {
            "tourism": _SCENIC_TOURISM,
            "historic": _SCENIC_HISTORIC,
            "natural": _SCENIC_NATURAL,
        }
        minx, miny, maxx, maxy = buffer_poly.bounds

        try:
            gdf = ox.features_from_bbox(bbox=(minx, miny, maxx, maxy), tags=tags)
        except Exception:
            return []

        _GENERIC_VALUES = {"yes", "no", "true", "false", "tourism", "historic", "natural"}

        pois: list[POI] = []
        for _, row in gdf.iterrows():
            name = row.get("name")
            if pd.isna(name):
                continue
            name = str(name).strip()
            if len(name) < 3 or name.lower() in _GENERIC_VALUES:
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
