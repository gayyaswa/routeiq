from __future__ import annotations
import json

import requests
from langchain_core.tools import tool

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "RouteIQ/1.0 (guruplace04@gmail.com)"}

# OSM feature classes we treat as visitable POIs
_ACCEPTED_CLASSES = {"tourism", "historic", "natural", "amenity", "leisure", "building"}


@tool
def search_poi_by_name(name: str, city: str) -> str:
    """Geocode a specific named place and return it as a POI dict for the itinerary.

    Use this when the user requests a specific landmark by name during refinement
    (e.g. "add Lombard Street", "include the Ferry Building").

    Args:
        name: The landmark name to search for, e.g. "Lombard Street"
        city: City context to constrain the search, e.g. "San Francisco, CA"

    Returns:
        JSON with a single POI dict (name, lat, lon, category, osm_id, subtype)
        or {"error": "..."} if not found.
    """
    params = {
        "q": f"{name}, {city}",
        "format": "jsonv2",
        "limit": 5,
        "addressdetails": 0,
        "extratags": 1,
    }
    try:
        resp = requests.get(_NOMINATIM_URL, params=params, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        results = resp.json()
    except Exception as exc:
        return json.dumps({"error": f"Nominatim request failed: {exc}"})

    if not results:
        return json.dumps({"error": f"No results found for '{name}' in {city}"})

    # Prefer results whose class is a known POI type; fall back to first result
    best = next(
        (r for r in results if r.get("category") in _ACCEPTED_CLASSES),
        results[0],
    )

    category = best.get("category", "tourism")
    if category not in ("tourism", "historic", "natural"):
        category = "tourism"

    osm_type = best.get("osm_type", "node")
    osm_id = f"{osm_type}/{best.get('osm_id', '0')}"
    subtype = best.get("type") or best.get("extratags", {}).get("tourism")

    return json.dumps({
        "name": best.get("display_name", name).split(",")[0].strip(),
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
        "category": category,
        "osm_id": osm_id,
        "subtype": subtype,
        "wikipedia_tag": best.get("extratags", {}).get("wikipedia"),
        "image_url": None,
        "description": None,
    })
