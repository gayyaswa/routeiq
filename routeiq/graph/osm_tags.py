"""OSM tag definitions — single source of truth for Overpass fetches and POI ingestion.

Imported by POIFinder (live queries + master file) and scripts/seed_poi_cache.py.
Every subtype listed here has a matching score in routeiq/routing/scenic_scores.py.
"""
from __future__ import annotations

# Keys and allowed values sent to Overpass / ox.features_from_bbox.
OSM_TAGS: dict[str, list[str]] = {
    "tourism": [
        "viewpoint", "museum", "attraction", "aquarium", "zoo",
        "theme_park", "lighthouse", "monument", "winery", "gallery",
    ],
    "historic": [
        "castle", "fort", "monument", "memorial", "ruins",
        "archaeological_site", "lighthouse", "manor", "battlefield",
        "landmark", "district", "church", "ship",
    ],
    "natural": [
        "peak", "volcano", "beach", "cape", "cliff", "waterfall",
        "hot_spring", "cave_entrance", "bay", "glacier", "wood",
        "lake", "dune",
    ],
    "leisure": ["nature_reserve", "park", "garden"],
    "amenity": ["theatre", "arts_centre"],
}

# For historic/tourism/natural the OSM key IS the POI category.
# leisure and amenity rows are remapped to existing POI categories at ingestion time.
LEISURE_CATEGORY: dict[str, str] = {
    "nature_reserve": "natural",
    "park": "natural",
    "garden": "tourism",
}
AMENITY_CATEGORY: dict[str, str] = {
    "theatre": "tourism",
    "arts_centre": "tourism",
}

# OSM tag values too generic to be useful POI subtypes — filtered at ingestion.
GENERIC_VALUES: frozenset[str] = frozenset({
    "yes", "no", "true", "false", "tourism", "historic", "natural",
})
