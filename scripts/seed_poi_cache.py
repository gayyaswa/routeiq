#!/usr/bin/env python3
"""
Pre-generate Bay Area POI master cache for demo reliability.

Strategy
--------
Instead of querying Overpass per-route at demo time (slow, unreliable), build a master
file of all qualifying Bay Area POIs and commit it to the repo.
POIFinder.find_pois() loads this file and does in-memory spatial filtering —
zero Overpass calls during any Bay Area demo query.

Two modes
---------
bootstrap (default)
    Merges all existing per-route cache JSONs in cache/pois/ into the master file.
    Instant, no Overpass calls. Covers all 5 demo routes immediately.

tiles
    Fetches ALL qualifying POIs for the Bay Area in 4 geographic tiles via Overpass,
    producing broader coverage for any route in the Bay Area (not just the 5 demo routes).
    Takes 3-5 minutes. Run offline before demo.

Usage:
    python3 scripts/seed_poi_cache.py              # bootstrap from existing caches
    python3 scripts/seed_poi_cache.py --tiles      # full tile fetch (broader coverage)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gzip
import json
import dataclasses
import time
import pandas as pd
import osmnx as ox

from routeiq.graph.poi import POI

_CACHE_DIR = "./cache/pois"
_MASTER_FILE = os.path.join(_CACHE_DIR, "bay_area_all.json.gz")

# Bay Area bounding box — files outside this are skipped during bootstrap
_BAY_AREA_NORTH = 39.0
_BAY_AREA_SOUTH = 36.5
_BAY_AREA_EAST = -120.5
_BAY_AREA_WEST = -123.5

# Must stay in sync with POIFinder._TAGS
_TAGS = {
    "tourism": [
        "viewpoint", "museum", "attraction", "aquarium", "zoo",
        "theme_park", "lighthouse", "monument", "winery",
    ],
    "historic": [
        "castle", "fort", "monument", "memorial", "ruins",
        "archaeological_site", "lighthouse", "manor", "battlefield",
    ],
    "natural": [
        "peak", "volcano", "beach", "cape", "cliff", "waterfall",
        "hot_spring", "cave_entrance", "bay", "glacier", "wood",
    ],
}
_GENERIC_VALUES = {"yes", "no", "true", "false", "tourism", "historic", "natural"}

# Smaller tiles sized to stay under 60s per Overpass query.
# Covers all 5 demo route corridors: SF→Muir Woods, SF→Napa, SJ→Santa Cruz,
# SF→Half Moon Bay, SF→Sausalito.
_BAY_AREA_TILES = [
    # (name, west, south, east, north)
    ("SF + Marin Headlands + Half Moon Bay",  -122.75, 37.35, -122.10, 38.05),
    ("Napa + Sonoma corridor",                -122.60, 38.00, -122.10, 38.75),
    ("East Bay + Tri-Valley",                 -122.40, 37.35, -121.55, 37.85),
    ("South Bay + Santa Cruz (west)",         -122.20, 36.85, -121.75, 37.45),
    ("South Bay + Santa Cruz (east)",         -121.90, 36.85, -121.55, 37.45),
]

_OVERPASS_MIRRORS = [
    "https://lz4.overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass-api.de/api",
]


# ── Bootstrap (fast, no Overpass) ─────────────────────────────────────────────

def _is_bay_area_file(filename: str) -> bool:
    """Return True if the per-route cache filename is a Bay Area corridor file."""
    # filename: pois_n{maxy:.3f}_s{miny:.3f}_e{maxx:.3f}_w{minx:.3f}.json[.gz]
    if not filename.startswith("pois_n"):
        return False
    stem = filename
    for ext in (".json.gz", ".json"):
        if filename.endswith(ext):
            stem = filename[len("pois_"):-len(ext)]
            break
    else:
        return False
    try:
        parts = stem.split("_")
        coords = {p[0]: float(p[1:]) for p in parts}
        return (
            _BAY_AREA_SOUTH <= coords["s"] <= _BAY_AREA_NORTH
            and _BAY_AREA_WEST <= coords["w"] <= _BAY_AREA_EAST
        )
    except (KeyError, ValueError):
        return False


def _load_route_cache(path: str) -> list[POI]:
    if path.endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return [POI(**d) for d in json.loads(f.read())]
    with open(path) as f:
        return [POI(**d) for d in json.load(f)]


def bootstrap_from_caches() -> None:
    """Merge all existing Bay Area per-route caches (.json.gz or .json) into the master file."""
    print("=" * 65)
    print("  Bootstrap: merging per-route caches → bay_area_all.json.gz")
    print("=" * 65)

    route_files = sorted(
        f for f in os.listdir(_CACHE_DIR)
        if _is_bay_area_file(f) and f != os.path.basename(_MASTER_FILE)
    )
    if not route_files:
        print("  No per-route cache files found. Run with --tiles to fetch from Overpass.")
        sys.exit(1)

    print(f"  Found {len(route_files)} Bay Area route cache files:")
    all_pois: list[POI] = []
    seen_osm_ids: set[str] = set()

    for fname in route_files:
        path = os.path.join(_CACHE_DIR, fname)
        pois = _load_route_cache(path)
        added = 0
        for p in pois:
            if p.osm_id not in seen_osm_ids:
                seen_osm_ids.add(p.osm_id)
                all_pois.append(p)
                added += 1
        print(f"    {fname}: {len(pois)} POIs → {added} new unique (total: {len(all_pois)})")

    _write_master(all_pois)


# ── Full tile fetch (broader, requires Overpass) ───────────────────────────────

def _gdf_to_pois(gdf) -> list[POI]:
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
    return pois


def _fetch_tile(west: float, south: float, east: float, north: float) -> object:
    """Try each Overpass mirror in order; return GeoDataFrame or raise."""
    for mirror in _OVERPASS_MIRRORS:
        ox.settings.overpass_url = mirror
        ox.settings.overpass_rate_limit = False
        ox.settings.requests_timeout = 90
        ox.settings.requests_max_retries = 0
        ox.settings.overpass_settings = "[out:json][timeout:85]"
        try:
            t0 = time.perf_counter()
            gdf = ox.features_from_bbox(bbox=(west, south, east, north), tags=_TAGS)
            print(f"    {mirror}: {time.perf_counter()-t0:.1f}s → {len(gdf)} rows", flush=True)
            return gdf
        except Exception as e:
            print(f"    {mirror}: FAILED ({e})", flush=True)
            time.sleep(5)
    raise RuntimeError("All Overpass mirrors failed for this tile")


def tile_fetch() -> None:
    """Fetch all qualifying Bay Area POIs in tiles and write the master file."""
    print("=" * 65)
    print("  Tile fetch: querying Overpass for full Bay Area POI coverage")
    print("=" * 65)

    all_pois: list[POI] = []
    seen_osm_ids: set[str] = set()
    failed_tiles: list[str] = []

    for tile_name, west, south, east, north in _BAY_AREA_TILES:
        print(f"\n  [{tile_name}]")
        print(f"    bbox W{west} S{south} E{east} N{north}")
        try:
            gdf = _fetch_tile(west, south, east, north)
        except RuntimeError as e:
            print(f"    SKIPPED: {e}")
            failed_tiles.append(tile_name)
            time.sleep(10)
            continue

        tile_pois = _gdf_to_pois(gdf)
        added = sum(
            1 for p in tile_pois
            if p.osm_id not in seen_osm_ids and not seen_osm_ids.add(p.osm_id)  # type: ignore[func-returns-value]
            and all_pois.append(p) is None  # type: ignore[func-returns-value]
        )
        print(f"    Qualified: {len(tile_pois)} → {added} new unique (total: {len(all_pois)})")
        time.sleep(3)  # be polite between tiles

    if failed_tiles:
        print(f"\n  WARNING: {len(failed_tiles)} tile(s) failed: {failed_tiles}")
        print("  Bootstrapping failed tiles from existing per-route caches…")
        _merge_route_caches_into(all_pois, seen_osm_ids)

    _write_master(all_pois)


def _merge_route_caches_into(all_pois: list[POI], seen_osm_ids: set[str]) -> None:
    route_files = [
        f for f in os.listdir(_CACHE_DIR)
        if _is_bay_area_file(f) and f != os.path.basename(_MASTER_FILE)
    ]
    for fname in route_files:
        for p in _load_route_cache(os.path.join(_CACHE_DIR, fname)):
            if p.osm_id not in seen_osm_ids:
                seen_osm_ids.add(p.osm_id)
                all_pois.append(p)


# ── Shared ────────────────────────────────────────────────────────────────────

def _write_master(all_pois: list[POI]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    raw_bytes = json.dumps([dataclasses.asdict(p) for p in all_pois]).encode()
    with gzip.open(_MASTER_FILE, "wb") as f:
        f.write(raw_bytes)
    raw_kb = len(raw_bytes) / 1024
    gz_kb = os.path.getsize(_MASTER_FILE) / 1024
    wikipedia_tagged = sum(1 for p in all_pois if p.wikipedia_tag)
    print(f"\n  Written: {_MASTER_FILE}")
    print(f"  Total unique POIs: {len(all_pois)}")
    print(f"  Size: {raw_kb:.0f} KB raw → {gz_kb:.0f} KB gzip ({100*gz_kb/raw_kb:.0f}% of raw)")
    print(f"  With wikipedia_tag: {wikipedia_tagged} ({100*wikipedia_tagged//max(len(all_pois),1)}%)")
    print("  POIFinder will use this file for all Bay Area queries — no Overpass at demo time.")


def main() -> None:
    print("RouteIQ Bay Area POI seeder\n")
    use_tiles = "--tiles" in sys.argv
    if use_tiles:
        tile_fetch()
    else:
        bootstrap_from_caches()
    print("\nDone. Commit cache/pois/bay_area_all.json.gz to the repo.")


if __name__ == "__main__":
    main()
