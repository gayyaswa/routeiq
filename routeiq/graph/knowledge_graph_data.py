"""Seed data for the RouteIQ knowledge graph — Bay Area POIs, Cities, Regions, Categories."""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

CATEGORIES = [
    {"name": "historic"},
    {"name": "natural"},
    {"name": "tourism"},
    {"name": "winery"},
    {"name": "state_park"},
    {"name": "mission"},
]

REGIONS = [
    {"name": "San Francisco",     "type": "city_region"},
    {"name": "North Bay / Marin", "type": "scenic_region"},
    {"name": "East Bay",          "type": "urban_region"},
    {"name": "Peninsula",         "type": "scenic_region"},
    {"name": "South Bay",         "type": "urban_region"},
    {"name": "Wine Country",      "type": "scenic_region"},
    {"name": "Bay Area",          "type": "metro_region"},
]

CITIES = [
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

_VALID_CATEGORIES = {c["name"] for c in CATEGORIES}

# Anchor POIs — always present; used as fallback when master cache is missing.
# osm_ids match values in cache/pois/bay_area_all.json.gz for dedup consistency.
_ANCHOR_POIS: list[dict] = [
    {"osm_id": "('way', 370672707)",    "name": "Golden Gate Bridge",  "category": "tourism",  "lat": 37.8203, "lon": -122.4786},
    {"osm_id": "('relation', 5504536)", "name": "Fort Point",          "category": "historic", "lat": 37.8106, "lon": -122.4771},
    {"osm_id": "('way', 28824850)",     "name": "Coit Tower",          "category": "historic", "lat": 37.8024, "lon": -122.4058},
    {"osm_id": "('way', 288371295)",    "name": "Palace of Fine Arts",  "category": "tourism",  "lat": 37.8029, "lon": -122.4484},
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
    pois: list[dict] = []
    for p in raw:
        if not p.get("wikipedia_tag"):
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
            "lat": p["lat"],
            "lon": p["lon"],
            "city": city,
            "region": _CITY_REGIONS.get(city, "Bay Area"),
            "wikipedia_tag": p.get("wikipedia_tag"),
        })
    return pois


POIS = _load_bay_area_pois()

RELATIONSHIPS = (
    [(p["osm_id"], "LOCATED_IN", p["city"]) for p in POIS]
    + [
        (p["osm_id"], "HAS_CATEGORY", p["category"] if p["category"] in _VALID_CATEGORIES else "tourism")
        for p in POIS
    ]
    + [(city["name"], "IN_REGION", _CITY_REGIONS.get(city["name"], "Bay Area")) for city in CITIES]
    + [(city["name"], "IN_REGION", "Bay Area") for city in CITIES]
)
