from __future__ import annotations
import gzip
import json
import os
import time
import dataclasses
import threading
import pandas as pd
import osmnx as ox
from shapely.geometry import LineString, Point
from routeiq.graph.poi import POI
from routeiq.graph.graph_loader import _OVERPASS_ENDPOINTS

_PER_MIRROR_TIMEOUT = 30  # hard wall-clock limit per Overpass attempt, independent of OSMnx retry logic

# Pre-seeded Bay Area master POI file — committed to repo.
# When present, POIFinder skips Overpass entirely and does in-memory spatial filtering.
_MASTER_FILE = "bay_area_all.json.gz"

# Tag filters — must stay in sync with scripts/seed_poi_cache.py
_SCENIC_TOURISM = [
    "viewpoint", "museum", "attraction", "aquarium", "zoo",
    "theme_park", "lighthouse", "monument", "winery",
]
_SCENIC_HISTORIC = [
    "castle", "fort", "monument", "memorial", "ruins",
    "archaeological_site", "lighthouse", "manor", "battlefield",
]
_SCENIC_NATURAL = [
    "peak", "volcano", "beach", "cape", "cliff", "waterfall",
    "hot_spring", "cave_entrance", "bay", "glacier", "wood",
]
_TAGS = {
    "tourism": _SCENIC_TOURISM,
    "historic": _SCENIC_HISTORIC,
    "natural": _SCENIC_NATURAL,
}
_GENERIC_VALUES = {"yes", "no", "true", "false", "tourism", "historic", "natural"}


class OverpassUnavailableError(Exception):
    """Raised when every Overpass mirror times out or errors — distinct from an empty result."""


class POIFinder:
    """Spatially joins OSM features within a buffer around a route (Pipeline pattern)."""

    def __init__(self, buffer_km: float = 5.0, cache_dir: str = "./cache/pois"):
        self._buffer_km = buffer_km
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._master_path = os.path.join(cache_dir, _MASTER_FILE)

    def find_pois(
        self,
        route_coords: list[tuple[float, float]],
        progress_fn=None,
    ) -> list[POI]:
        t0 = time.perf_counter()
        if not route_coords:
            return []

        line = LineString([(lon, lat) for lat, lon in route_coords])
        buffer_deg = self._buffer_km / 111.0
        buffer_poly = line.buffer(buffer_deg)

        # --- Path 1: Bay Area master file (preferred — no Overpass call) ---
        if os.path.exists(self._master_path):
            result = self._filter_master(buffer_poly, t0)
            if result is not None:
                return result

        # --- Path 2: Per-route cache (fallback for non-Bay-Area routes) ---
        minx, miny, maxx, maxy = buffer_poly.bounds
        stem = f"pois_n{maxy:.3f}_s{miny:.3f}_e{maxx:.3f}_w{minx:.3f}"
        gz_path = os.path.join(self._cache_dir, f"{stem}.json.gz")
        json_path = os.path.join(self._cache_dir, f"{stem}.json")  # legacy

        if os.path.exists(gz_path):
            t1 = time.perf_counter()
            with gzip.open(gz_path, "rb") as f:
                pois = [POI(**d) for d in json.loads(f.read())]
            print(f"[timing]     poi per-route cache HIT (gz): {time.perf_counter()-t1:.2f}s → {len(pois)} POIs", flush=True)
            return pois
        if os.path.exists(json_path):
            t1 = time.perf_counter()
            with open(json_path) as f:
                pois = [POI(**d) for d in json.load(f)]
            print(f"[timing]     poi per-route cache HIT (json): {time.perf_counter()-t1:.2f}s → {len(pois)} POIs", flush=True)
            return pois

        # --- Path 3: Live Overpass query (fallback for uncached routes) ---
        return self._query_overpass(buffer_poly, gz_path, progress_fn, t0)

    def find_pois_in_bbox(
        self,
        south: float,
        north: float,
        west: float,
        east: float,
    ) -> list[POI]:
        """Find POIs within a lat/lon bounding box — used by the Day Trip agent."""
        from shapely.geometry import box
        bbox_poly = box(west, south, east, north)

        if os.path.exists(self._master_path):
            result = self._filter_master(bbox_poly, time.perf_counter())
            if result is not None:
                return result

        stem = f"pois_n{north:.3f}_s{south:.3f}_e{east:.3f}_w{west:.3f}"
        gz_path = os.path.join(self._cache_dir, f"{stem}.json.gz")
        json_path = os.path.join(self._cache_dir, f"{stem}.json")

        if os.path.exists(gz_path):
            with gzip.open(gz_path, "rb") as f:
                return [POI(**d) for d in json.loads(f.read())]
        if os.path.exists(json_path):
            with open(json_path) as f:
                return [POI(**d) for d in json.load(f)]

        return self._query_overpass(bbox_poly, gz_path, None, time.perf_counter())

    # ------------------------------------------------------------------

    def _filter_master(self, buffer_poly, t0: float) -> list[POI] | None:
        """Load master file and filter spatially. Returns None if master doesn't cover this area."""
        t1 = time.perf_counter()
        with gzip.open(self._master_path, "rb") as f:
            all_pois = [POI(**d) for d in json.loads(f.read())]
        load_s = time.perf_counter() - t1

        t1 = time.perf_counter()
        filtered = [p for p in all_pois if buffer_poly.contains(Point(p.lon, p.lat))]
        filter_s = time.perf_counter() - t1

        print(
            f"[timing]     poi master: load {load_s:.2f}s ({len(all_pois)} total) "
            f"+ filter {filter_s:.3f}s → {len(filtered)} in buffer",
            flush=True,
        )
        if not filtered:
            print("[timing]     poi master: 0 results — route outside master coverage, falling through", flush=True)
            return None
        print(f"[timing]   poi find_pois total: {time.perf_counter()-t0:.2f}s", flush=True)
        return filtered

    def _query_overpass(self, buffer_poly, cache_path: str, progress_fn, t0: float) -> list[POI]:
        minx, miny, maxx, maxy = buffer_poly.bounds
        print(f"[timing]     poi cache MISS — querying Overpass", flush=True)
        n_mirrors = len(_OVERPASS_ENDPOINTS)
        gdf = None

        for idx, mirror in enumerate(_OVERPASS_ENDPOINTS, 1):
            if progress_fn:
                progress_fn(f"Querying POI server {idx}/{n_mirrors}…")
            t1 = time.perf_counter()
            result_holder: list = [None]
            error_holder: list = [None]

            def _fetch(m=mirror, rh=result_holder, eh=error_holder):
                try:
                    ox.settings.overpass_url = m
                    rh[0] = ox.features_from_bbox(bbox=(minx, miny, maxx, maxy), tags=_TAGS)
                except Exception as exc:
                    eh[0] = exc

            fetch_thread = threading.Thread(target=_fetch, daemon=True)
            fetch_thread.start()
            fetch_thread.join(timeout=_PER_MIRROR_TIMEOUT)

            elapsed = time.perf_counter() - t1
            if fetch_thread.is_alive():
                print(f"[timing]     overpass {mirror}: TIMEOUT after {elapsed:.1f}s → next mirror", flush=True)
                if progress_fn:
                    progress_fn(f"POI server {idx}/{n_mirrors} timed out — trying backup…")
                continue
            if error_holder[0] is not None:
                print(f"[timing]     overpass {mirror}: FAILED after {elapsed:.2f}s ({error_holder[0]})", flush=True)
                if progress_fn:
                    progress_fn(f"POI server {idx}/{n_mirrors} unavailable — trying backup…")
                continue
            gdf = result_holder[0]
            print(f"[timing]     overpass {mirror}: {elapsed:.2f}s → {len(gdf)} rows", flush=True)
            break

        if gdf is None:
            raise OverpassUnavailableError(
                f"All {n_mirrors} Overpass mirrors timed out or failed. "
                "The OpenStreetMap POI service is temporarily unavailable."
            )

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
                category, subtype = "historic", str(row.get("historic"))
            elif pd.notna(row.get("tourism")):
                category, subtype = "tourism", str(row.get("tourism"))
            elif pd.notna(row.get("natural")):
                category, subtype = "natural", str(row.get("natural"))
            else:
                continue

            wikipedia_tag = row.get("wikipedia")
            if pd.isna(wikipedia_tag):
                wikipedia_tag = None

            pois.append(POI(
                name=str(name),
                category=category,
                lat=centroid.y,
                lon=centroid.x,
                osm_id=str(row.name),
                wikipedia_tag=wikipedia_tag,
                subtype=subtype,
            ))
        print(f"[timing]     spatial filter: {time.perf_counter()-t1:.2f}s → {len(pois)} POIs kept", flush=True)

        with gzip.open(cache_path, "wb") as f:
            f.write(json.dumps([dataclasses.asdict(p) for p in pois]).encode())
        print(f"[timing]   poi find_pois total: {time.perf_counter()-t0:.2f}s", flush=True)
        return pois
