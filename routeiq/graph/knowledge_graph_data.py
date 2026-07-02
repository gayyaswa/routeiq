"""Seed data for the RouteIQ knowledge graph — Bay Area + NYC POIs, Cities, Regions, Categories."""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

CATEGORIES = [
    {"name": "historic"},
    {"name": "natural"},
    {"name": "tourism"},
]

REGIONS = [
    {"name": "San Francisco",     "type": "city_region"},
    {"name": "North Bay / Marin", "type": "scenic_region"},
    {"name": "East Bay",          "type": "urban_region"},
    {"name": "Peninsula",         "type": "scenic_region"},
    {"name": "South Bay",         "type": "urban_region"},
    {"name": "Wine Country",      "type": "scenic_region"},
    {"name": "Bay Area",          "type": "metro_region"},
    # NYC
    {"name": "Manhattan",         "type": "city_region"},
    {"name": "Brooklyn",          "type": "urban_region"},
    {"name": "Queens",            "type": "urban_region"},
    {"name": "Bronx",             "type": "urban_region"},
    {"name": "Staten Island",     "type": "scenic_region"},
    {"name": "New York City",     "type": "metro_region"},
]

CITIES = [
    # Bay Area
    {"name": "San Francisco", "lat": 37.7749, "lon": -122.4194},
    {"name": "Oakland",       "lat": 37.8044, "lon": -122.2712},
    {"name": "Berkeley",      "lat": 37.8716, "lon": -122.2727},
    {"name": "San Jose",      "lat": 37.3382, "lon": -121.8863},
    {"name": "Santa Cruz",    "lat": 36.9741, "lon": -122.0308},
    {"name": "Sausalito",     "lat": 37.8590, "lon": -122.4852},
    {"name": "Napa",          "lat": 38.2975, "lon": -122.2869},
    {"name": "Half Moon Bay", "lat": 37.4636, "lon": -122.4286},
    {"name": "Mill Valley",   "lat": 37.9060, "lon": -122.5450},
    {"name": "Tiburon",       "lat": 37.8910, "lon": -122.4569},
    # NYC boroughs
    {"name": "Manhattan",     "lat": 40.7831, "lon": -73.9712},
    {"name": "Brooklyn",      "lat": 40.6782, "lon": -73.9442},
    {"name": "Queens",        "lat": 40.7282, "lon": -73.7949},
    {"name": "Bronx",         "lat": 40.8448, "lon": -73.8648},
    {"name": "Staten Island", "lat": 40.5795, "lon": -74.1502},
]

_CITY_REGIONS: dict[str, str] = {
    "San Francisco": "San Francisco",
    "Sausalito":     "North Bay / Marin",
    "Mill Valley":   "North Bay / Marin",
    "Tiburon":       "North Bay / Marin",
    "Oakland":       "East Bay",
    "Berkeley":      "East Bay",
    "Half Moon Bay": "Peninsula",
    "San Jose":      "South Bay",
    "Santa Cruz":    "South Bay",
    "Napa":          "Wine Country",
}

_NYC_CITY_REGIONS: dict[str, str] = {
    "Manhattan":     "Manhattan",
    "Brooklyn":      "Brooklyn",
    "Queens":        "Queens",
    "Bronx":         "Bronx",
    "Staten Island": "Staten Island",
}

_ALL_CITY_REGIONS: dict[str, str] = {**_CITY_REGIONS, **_NYC_CITY_REGIONS}

_VALID_CATEGORIES = {c["name"] for c in CATEGORIES}

# Anchor POIs — always present; used as fallback when master cache is missing.
# Also covers iconic landmarks OSM tags as infrastructure (Bay Bridge, Ferry Building)
# rather than tourism, so they'd otherwise be excluded from our POI fetch.
_ANCHOR_POIS: list[dict] = [
    # ── San Francisco ─────────────────────────────────────────────────────────
    {"osm_id": "('way', 370672707)",      "name": "Golden Gate Bridge",            "category": "tourism",  "lat": 37.8203,  "lon": -122.4786, "wikipedia_tag": "en:Golden Gate Bridge",                    "subtype": "attraction"},
    {"osm_id": "('relation', 5504536)",   "name": "Fort Point",                    "category": "historic", "lat": 37.8106,  "lon": -122.4771, "wikipedia_tag": "en:Fort Point, San Francisco",             "subtype": "attraction"},
    {"osm_id": "('way', 28824850)",       "name": "Coit Tower",                    "category": "historic", "lat": 37.8024,  "lon": -122.4058, "wikipedia_tag": "en:Coit Tower",                            "subtype": "attraction"},
    {"osm_id": "('way', 288371295)",      "name": "Palace of Fine Arts",           "category": "tourism",  "lat": 37.8029,  "lon": -122.4484, "wikipedia_tag": "en:Palace of Fine Arts",                   "subtype": "attraction"},
    {"osm_id": "anchor::bay_bridge_sf",   "name": "San Francisco-Oakland Bay Bridge", "category": "tourism", "lat": 37.7983, "lon": -122.3778, "wikipedia_tag": "en:San Francisco–Oakland Bay Bridge",      "subtype": "attraction"},
    {"osm_id": "anchor::ferry_building",  "name": "San Francisco Ferry Building",  "category": "tourism",  "lat": 37.7955,  "lon": -122.3937, "wikipedia_tag": "en:San Francisco Ferry Building",          "subtype": "attraction"},
    {"osm_id": "anchor::crissy_field",    "name": "Crissy Field",                  "category": "natural",  "lat": 37.8032,  "lon": -122.4669, "wikipedia_tag": "en:Crissy Field",                          "subtype": "park"},
    {"osm_id": "anchor::twin_peaks_sf",   "name": "Twin Peaks Scenic Overlook",    "category": "natural",  "lat": 37.7534,  "lon": -122.4478, "wikipedia_tag": "en:Twin Peaks (San Francisco)",            "subtype": "viewpoint"},
    {"osm_id": "anchor::haight_ashbury",  "name": "Haight-Ashbury",               "category": "tourism",  "lat": 37.7692,  "lon": -122.4481, "wikipedia_tag": "en:Haight-Ashbury",                        "subtype": "attraction"},
]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_city(lat: float, lon: float) -> str:
    best, best_d = "San Francisco", float("inf")
    for city in CITIES:
        d = _haversine(lat, lon, city["lat"], city["lon"])
        if d < best_d:
            best_d = d
            best = city["name"]
    return best


def _notability_sort_key(p: dict) -> tuple:
    """Sort key: en:wikipedia first, then other wiki, then no wiki; subtype tier within each group."""
    from routeiq.routing.scenic_scores import SUBTYPE_TIER
    wiki = p.get("wikipedia_tag") or ""
    wiki_rank = 0 if wiki.startswith("en:") else (1 if wiki else 2)
    return (wiki_rank, SUBTYPE_TIER.get(p.get("subtype") or "", 6))


def _dedup_and_sort(pois: list[dict]) -> list[dict]:
    """Deduplicate by name (keep first osm_id) then sort by notability."""
    seen_names: set[str] = set()
    deduped: list[dict] = []
    for p in pois:
        if p["name"] not in seen_names:
            seen_names.add(p["name"])
            deduped.append(p)
    deduped.sort(key=_notability_sort_key)
    return deduped


def _load_bay_area_pois() -> list[dict]:
    """Load OSM-verified notable Bay Area POIs from master cache; fallback to anchors."""
    master = Path(__file__).parent.parent.parent / "cache" / "pois" / "bay_area_all.json.gz"
    if not master.exists():
        anchors = [dict(p) for p in _ANCHOR_POIS]
        for p in anchors:
            p["city"] = _nearest_city(p["lat"], p["lon"])
            p["region"] = _CITY_REGIONS.get(p["city"], "Bay Area")
        return anchors

    with gzip.open(master) as f:
        raw = json.load(f)

    seen: set[str] = set()
    seen_names: set[str] = set()
    pois: list[dict] = []
    for p in raw:
        if not p.get("name") or not p.get("category"):
            continue
        osm_id = p["osm_id"]
        if osm_id in seen:
            continue
        seen.add(osm_id)
        seen_names.add(p["name"])
        city = _nearest_city(p["lat"], p["lon"])
        pois.append({
            "osm_id": osm_id,
            "name": p["name"],
            "category": p.get("category", "tourism"),
            "subtype": p.get("subtype"),
            "lat": p["lat"],
            "lon": p["lon"],
            "city": city,
            "region": _CITY_REGIONS.get(city, "Bay Area"),
            "wikipedia_tag": p.get("wikipedia_tag"),
        })

    # Always merge anchors — ensures iconic landmarks missing from OSM tourism tags
    # (Bay Bridge, Ferry Building, etc.) are present regardless of the master cache.
    anchor_by_name = {p["name"]: p for p in _ANCHOR_POIS}

    # Patch wikipedia_tag onto existing OSM entries that are missing it.
    for existing in pois:
        anchor = anchor_by_name.get(existing["name"])
        if anchor and anchor.get("wikipedia_tag") and not existing.get("wikipedia_tag"):
            existing["wikipedia_tag"] = anchor["wikipedia_tag"]

    # Add anchors whose name isn't in the OSM cache at all.
    for p in _ANCHOR_POIS:
        if p["osm_id"] in seen or p["name"] in seen_names:
            continue
        entry = dict(p)
        entry["city"] = _nearest_city(p["lat"], p["lon"])
        entry["region"] = _CITY_REGIONS.get(entry["city"], "Bay Area")
        pois.append(entry)

    return _dedup_and_sort(pois)


def _load_nyc_pois() -> list[dict]:
    """Load NYC POIs from bbox cache files; gate on name + category."""
    cache_dir = Path(__file__).parent.parent.parent / "cache" / "pois"
    nyc_files = [
        cache_dir / "pois_n40.813_s40.513_e-73.789_w-74.089.json.gz",
        cache_dir / "pois_n40.818_s40.518_e-73.829_w-74.129.json.gz",
    ]

    seen: set[str] = set()
    pois: list[dict] = []
    for cache_file in nyc_files:
        if not cache_file.exists():
            continue
        with gzip.open(cache_file) as f:
            raw = json.load(f)
        for p in raw:
            if not p.get("name") or not p.get("category"):
                continue
            osm_id = p["osm_id"]
            if osm_id in seen:
                continue
            seen.add(osm_id)
            city = _nearest_city(p["lat"], p["lon"])
            pois.append({
                "osm_id": osm_id,
                "name": p["name"],
                "category": p.get("category", "tourism"),
                "subtype": p.get("subtype"),
                "lat": p["lat"],
                "lon": p["lon"],
                "city": city,
                "region": _NYC_CITY_REGIONS.get(city, "New York City"),
                "wikipedia_tag": p.get("wikipedia_tag"),
            })
    return _dedup_and_sort(pois)


POIS = _load_bay_area_pois() + _load_nyc_pois()

RELATIONSHIPS = (
    [(p["osm_id"], "LOCATED_IN", p["city"]) for p in POIS]
    + [
        (p["osm_id"], "HAS_CATEGORY", p["category"] if p["category"] in _VALID_CATEGORIES else "tourism")
        for p in POIS
    ]
    # Specific sub-region edge (e.g. Sausalito→North Bay/Marin; Manhattan→Manhattan)
    + [(city["name"], "IN_REGION", _ALL_CITY_REGIONS.get(city["name"], "Bay Area")) for city in CITIES]
    # Metro umbrella — Bay Area cities also point to "Bay Area"
    + [(city["name"], "IN_REGION", "Bay Area") for city in CITIES if city["name"] in _CITY_REGIONS]
    # NYC metro umbrella — boroughs also point to "New York City"
    + [(city["name"], "IN_REGION", "New York City") for city in CITIES if city["name"] in _NYC_CITY_REGIONS]
)
