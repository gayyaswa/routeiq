from __future__ import annotations
import json
import os
import time
import dataclasses
import threading
import pandas as pd
import osmnx as ox
from shapely.geometry import LineString
from routeiq.graph.poi import POI
from routeiq.graph.graph_loader import _OVERPASS_MIRRORS

_PER_MIRROR_TIMEOUT = 30  # hard wall-clock limit per Overpass attempt, independent of OSMnx retry logic


class POIFinder:
    """Spatially joins OSM features within a buffer around a route (Pipeline pattern)."""

    def __init__(self, buffer_km: float = 5.0, cache_dir: str = "./cache/pois"):
        self._buffer_km = buffer_km
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def find_pois(self, route_coords: list[tuple[float, float]]) -> list[POI]:
        t0 = time.perf_counter()
        if not route_coords:
            return []

        t1 = time.perf_counter()
        line = LineString([(lon, lat) for lat, lon in route_coords])
        buffer_deg = self._buffer_km / 111.0
        buffer_poly = line.buffer(buffer_deg)
        print(f"[timing]     poi buffer build: {time.perf_counter()-t1:.2f}s ({len(route_coords)} coords)", flush=True)

        # Scenic tourism subtypes only — excludes hotels, hostels, artwork, campsites
        _SCENIC_TOURISM = [
            "viewpoint", "museum", "attraction", "aquarium", "zoo",
            "theme_park", "lighthouse", "monument", "winery",
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
        cache_key = f"pois_n{maxy:.3f}_s{miny:.3f}_e{maxx:.3f}_w{minx:.3f}.json"
        cache_path = os.path.join(self._cache_dir, cache_key)

        if os.path.exists(cache_path):
            t1 = time.perf_counter()
            with open(cache_path) as f:
                pois = [POI(**d) for d in json.load(f)]
            print(f"[timing]     poi cache HIT: {time.perf_counter()-t1:.2f}s → {len(pois)} POIs", flush=True)
            return pois

        print(f"[timing]     poi cache MISS — querying Overpass", flush=True)
        gdf = None
        for mirror in _OVERPASS_MIRRORS:
            t1 = time.perf_counter()
            result_holder: list = [None]
            error_holder: list = [None]

            def _fetch(m=mirror, rh=result_holder, eh=error_holder):
                try:
                    ox.settings.overpass_url = m
                    rh[0] = ox.features_from_bbox(bbox=(minx, miny, maxx, maxy), tags=tags)
                except Exception as exc:
                    eh[0] = exc

            fetch_thread = threading.Thread(target=_fetch, daemon=True)
            fetch_thread.start()
            fetch_thread.join(timeout=_PER_MIRROR_TIMEOUT)

            elapsed = time.perf_counter() - t1
            if fetch_thread.is_alive():
                print(f"[timing]     overpass {mirror}: TIMEOUT after {elapsed:.1f}s → next mirror", flush=True)
                continue
            if error_holder[0] is not None:
                print(f"[timing]     overpass {mirror}: FAILED after {elapsed:.2f}s ({error_holder[0]})", flush=True)
                continue
            gdf = result_holder[0]
            print(f"[timing]     overpass {mirror}: {elapsed:.2f}s → {len(gdf)} rows", flush=True)
            break
        if gdf is None:
            return []

        _GENERIC_VALUES = {"yes", "no", "true", "false", "tourism", "historic", "natural"}

        t1 = time.perf_counter()
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
        print(f"[timing]     spatial filter: {time.perf_counter()-t1:.2f}s → {len(pois)} POIs kept", flush=True)

        with open(cache_path, "w") as f:
            json.dump([dataclasses.asdict(p) for p in pois], f)
        print(f"[timing]   poi find_pois total: {time.perf_counter()-t0:.2f}s", flush=True)
        return pois
