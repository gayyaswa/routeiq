from __future__ import annotations
import json
import math

from langchain_core.tools import tool

_SPEED_KMH = 30.0       # urban / scenic driving average
_OVERHEAD_MIN = 5.0     # parking + transitions


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


@tool
def get_travel_time(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Estimate driving time between two lat/lon points (point-to-point, not detour-from-route).

    Args:
        lat1: Origin latitude
        lon1: Origin longitude
        lat2: Destination latitude
        lon2: Destination longitude

    Returns:
        JSON with distance_km (float) and estimated_minutes (float).
    """
    km = _haversine_km(lat1, lon1, lat2, lon2)
    minutes = (km / _SPEED_KMH) * 60 + _OVERHEAD_MIN
    return json.dumps({"distance_km": round(km, 2), "estimated_minutes": round(minutes, 1)})
