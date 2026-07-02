"""Shared OSM subtype → experiential quality scores (Registry pattern).

Single source of truth for both POISelector and ActivityPOISelector.
"""
from __future__ import annotations

SCENIC_SCORE: dict[str, int] = {
    # natural — landscapes and geological features
    "waterfall": 9, "volcano": 9, "beach": 9, "cape": 9,
    "peak": 8, "cliff": 8, "glacier": 8, "hot_spring": 8,
    "lake": 8,
    "bay": 7, "cave_entrance": 7, "wood": 6, "dune": 6,
    # leisure — mapped to natural/tourism at ingestion time
    "nature_reserve": 9,   # Muir Woods, Point Reyes, Tilden Park
    "park": 7,             # Golden Gate Park, Central Park, Dolores Park
    "garden": 6,           # Japanese Tea Garden, Botanical Garden
    # tourism — experiential destinations
    "viewpoint": 9, "lighthouse": 8,
    "attraction": 7, "museum": 6, "winery": 6,
    "gallery": 6,          # art galleries
    "aquarium": 6, "zoo": 5, "theme_park": 5,
    "monument": 4,
    # historic — built heritage
    "castle": 8, "fort": 7, "ruins": 7, "archaeological_site": 7,
    "landmark": 7,         # famous historic buildings/sites
    "manor": 6, "battlefield": 6,
    "district": 5,         # Haight-Ashbury, Chinatown, Mission District
    "church": 5,           # Mission Dolores, Grace Cathedral
    "ship": 5,             # USS Midway, historic vessels
    # amenity — mapped to tourism at ingestion time
    "theatre": 5,          # historic theaters, opera houses
    "arts_centre": 5,      # cultural centers
    "memorial": 3,
}

_DEFAULT_SCENIC = 5

# Lower tier = better — used for notability-based KG sort order.
# POIs with the same wikipedia tier are secondarily sorted by this.
SUBTYPE_TIER: dict[str, int] = {
    "attraction": 0, "nature_reserve": 0,
    "museum": 1, "park": 1,
    "viewpoint": 2, "lighthouse": 2, "castle": 2, "fort": 2,
    "ruins": 2, "gallery": 2, "landmark": 2,
    "monument": 3, "church": 3,
    "memorial": 4, "peak": 5, "bay": 5, "district": 5,
}


def get_scenic_score(subtype: str | None) -> int:
    """Return the experiential quality score for an OSM subtype."""
    return SCENIC_SCORE.get(subtype or "", _DEFAULT_SCENIC)
