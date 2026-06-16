from __future__ import annotations
import json

from langchain_core.tools import tool

_VISIT_MINUTES: dict[str, int] = {
    "museum":              90,
    "aquarium":            90,
    "zoo":                120,
    "winery":              60,
    "castle":              60,
    "park":                60,
    "beach":               60,
    "ruins":               45,
    "archaeological_site": 45,
    "waterfall":           30,
    "viewpoint":           30,
    "lighthouse":          25,
    "monument":            20,
    "memorial":            20,
}
_DEFAULT_MINUTES = 45


@tool
def estimate_visit_duration(category: str, subtype: str) -> str:
    """Estimate how long a visitor typically spends at a POI.

    Args:
        category: OSM category — "tourism", "historic", or "natural"
        subtype: OSM value — e.g. "museum", "viewpoint", "beach", "ruins"

    Returns:
        JSON with estimated_minutes (int).
    """
    minutes = _VISIT_MINUTES.get(subtype.lower(), _DEFAULT_MINUTES)
    return json.dumps({"estimated_minutes": minutes})
