from __future__ import annotations
from dataclasses import dataclass


@dataclass
class POI:
    """A point of interest extracted from OSM features along a route (dataclass)."""

    name: str
    category: str  # "historic" | "tourism" | "natural"
    lat: float
    lon: float
    osm_id: str
    wikipedia_tag: str | None = None  # populated by RAG layer on Day 3
    image_url: str | None = None      # Wikipedia thumbnail, populated on Day 3
    description: str | None = None   # Wikipedia extract, populated on Day 3
    subtype: str | None = None        # OSM value: "viewpoint", "beach", "fort", etc.
