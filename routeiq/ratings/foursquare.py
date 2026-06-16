from __future__ import annotations
import json
import math
import os
import time
from typing import Any

import chromadb
import requests

from routeiq.graph.poi import POI
from routeiq.ratings.base import POIRatingProvider, RatedPOI

_CACHE_DIR = "./cache/ratings"
_CACHE_TTL_SECONDS = 21 * 86400      # 21 days — instructors never hit live API
_API_URL = "https://api.foursquare.com/v3/places/search"
_SIMILARITY_THRESHOLD = 0.6          # ChromaDB L2 distance; lower = closer match
_PROXIMITY_KM = 0.1                  # 100 m proximity fallback

# 3 Foursquare category buckets that cover OSM tourism / historic / natural
_CATEGORY_BUCKETS: dict[str, str] = {
    "sights":   "16000",   # Landmarks and Outdoors (viewpoints, monuments, nature)
    "arts":     "12000",   # Arts and Entertainment (museums, galleries)
    "historic": "12013",   # Historic and Protected Site
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


class FoursquareRatingProvider(POIRatingProvider):
    """Enriches OSM POIs with Foursquare ratings via batch category search + ChromaDB name merge (Strategy pattern)."""

    def __init__(self, api_key: str, cache_dir: str = _CACHE_DIR):
        self._api_key = api_key
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        fs_pool: list[dict[str, Any]] = []
        for bucket_name in _CATEGORY_BUCKETS:
            fs_pool.extend(self._fetch_category(city, bucket_name))

        if not fs_pool:
            return [RatedPOI(poi=p) for p in pois]

        collection = self._build_index(fs_pool)
        return [self._make_rated(poi, fs_pool, collection) for poi in pois]

    def _fetch_category(self, city: str, cat: str) -> list[dict[str, Any]]:
        cache_path = self._cache_path(city, cat)
        cutoff = time.time() - _CACHE_TTL_SECONDS

        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > cutoff:
            with open(cache_path) as f:
                return json.load(f)

        data = self._call_api(city, cat)
        with open(cache_path, "w") as f:
            json.dump(data, f)
        return data

    def _call_api(self, city: str, cat: str) -> list[dict[str, Any]]:
        params = {
            "near": city,
            "categories": _CATEGORY_BUCKETS[cat],
            "fields": "name,geocodes,rating,stats,hours,tips",
            "limit": 50,
        }
        # Foursquare v3: raw API key in Authorization header — NOT "Bearer KEY"
        headers = {"Authorization": self._api_key, "Accept": "application/json"}
        try:
            resp = requests.get(_API_URL, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception as exc:
            print(f"[foursquare] API error for {city}/{cat}: {exc}", flush=True)
            return []

    def _build_index(self, fs_pool: list[dict[str, Any]]) -> Any:
        import uuid
        client = chromadb.EphemeralClient()
        # Unique name per call — EphemeralClient is a process-level singleton, so
        # reusing "fs_merge" would collide across enrich_batch calls in the same process.
        collection = client.create_collection(f"fs_merge_{uuid.uuid4().hex}")
        names = [item.get("name", "") for item in fs_pool]
        ids = [str(i) for i in range(len(fs_pool))]
        collection.add(documents=names, ids=ids)
        return collection

    def _make_rated(self, poi: POI, fs_pool: list[dict[str, Any]], collection: Any) -> RatedPOI:
        match = self._find_match(poi, fs_pool, collection)
        if match is None:
            return RatedPOI(poi=poi)

        raw_rating = match.get("rating")
        rating = raw_rating / 2.0 if isinstance(raw_rating, (int, float)) else None

        stats = match.get("stats") or {}
        review_count = stats.get("total_ratings") or stats.get("total_tips")

        snippet: str | None = None
        tips = match.get("tips")
        if tips and isinstance(tips, list) and tips:
            snippet = tips[0].get("text")

        hours_obj = match.get("hours") or {}
        display = hours_obj.get("display")
        if isinstance(display, list):
            hours = display[0] if display else None
        else:
            hours = display

        return RatedPOI(poi=poi, rating=rating, review_count=review_count,
                        review_snippet=snippet, hours=hours)

    def _find_match(self, poi: POI, fs_pool: list[dict[str, Any]], collection: Any) -> dict[str, Any] | None:
        results = collection.query(query_texts=[poi.name], n_results=1)
        distances = results["distances"][0]
        ids = results["ids"][0]

        if distances and distances[0] <= _SIMILARITY_THRESHOLD:
            return fs_pool[int(ids[0])]

        # Proximity fallback: nearest Foursquare item within 100 m
        best_km = float("inf")
        best: dict[str, Any] | None = None
        for item in fs_pool:
            geo = (item.get("geocodes") or {}).get("main") or {}
            lat = geo.get("latitude")
            lon = geo.get("longitude")
            if lat is None or lon is None:
                continue
            km = _haversine_km(poi.lat, poi.lon, lat, lon)
            if km < best_km:
                best_km = km
                best = item
        return best if best_km <= _PROXIMITY_KM else None

    def _cache_path(self, city: str, cat: str) -> str:
        safe_city = city.replace(" ", "_").replace(",", "").lower()
        return os.path.join(self._cache_dir, f"foursquare_{safe_city}_{cat}.json")
