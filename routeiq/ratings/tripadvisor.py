from __future__ import annotations
import json
import math
import os
import time
import uuid
from typing import Any

import chromadb
import requests

from routeiq.graph.poi import POI
from routeiq.ratings.base import POIRatingProvider, RatedPOI

_CACHE_DIR = "./cache/ratings"
_CACHE_TTL_SECONDS = 21 * 86400          # 21 days — instructors never hit live API
_API_BASE = "https://terra.tripadvisor.com/api"
_SIMILARITY_THRESHOLD = 0.6              # ChromaDB L2 distance; lower = closer match
_PROXIMITY_KM = 0.1                      # 100 m — geographic fallback when names diverge
_MAX_REVIEWS = 3
_MIN_REVIEW_CHARS = 80                   # filter one-liners before passing to LLM
_MAX_PHOTOS = 5
_MAX_RADIUS_KM = 8                       # Terra API hard limit


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


class TripAdvisorRatingProvider(POIRatingProvider):
    """Enriches OSM POIs with TripAdvisor ratings, reviews, and photos via Terra API (Strategy pattern)."""

    def __init__(self, api_key: str, cache_dir: str = _CACHE_DIR):
        self._api_key = api_key
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-KEY": self._api_key, "Accept": "application/json"}

    @property
    def source_name(self) -> str:
        return "TripAdvisor"

    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        if not pois:
            return []
        return [self._enrich_poi(poi) for poi in pois]

    # ── Per-POI fetch ─────────────────────────────────────────────────────────

    def _enrich_poi(self, poi: POI) -> RatedPOI:
        """Search TripAdvisor near the POI's own coordinates and return enriched result."""
        pool = self._fetch_nearby_poi(poi)
        if not pool:
            return RatedPOI(poi=poi, review_source=self.source_name)
        collection = self._build_index(pool)
        return self._make_rated(poi, pool, collection)

    def _fetch_nearby_poi(self, poi: POI) -> list[dict[str, Any]]:
        """Fetch and cache the TripAdvisor nearby pool for a single POI."""
        cache_path = self._poi_cache_path(poi)
        cutoff = time.time() - _CACHE_TTL_SECONDS

        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > cutoff:
            with open(cache_path) as f:
                return json.load(f)

        data = self._call_nearby(poi.lat, poi.lon)
        with open(cache_path, "w") as f:
            json.dump(data, f)
        return data

    def _call_nearby(self, lat: float, lon: float) -> list[dict[str, Any]]:
        params = {
            "lat": lat,
            "lon": lon,
            "radius": 1,
            "unit": "KM",
            "category": "ATTRACTION",
            "size": 20,
        }
        try:
            resp = requests.get(
                f"{_API_BASE}/locations/nearby",
                headers=self._headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("data", [])
            return [self._normalize_location(item["location"])
                    for item in items if "location" in item]
        except Exception as exc:
            print(f"[tripadvisor] nearby_search error: {exc}", flush=True)
            return []

    def _normalize_location(self, loc: dict[str, Any]) -> dict[str, Any]:
        """Flatten Terra API location object to the same shape the rest of the pipeline expects."""
        name = next((n["value"] for n in loc.get("names", []) if n.get("primary")), "")
        coords = loc.get("coordinates") or {}
        overall = (loc.get("traveler_ratings") or {}).get("overall") or {}
        return {
            "location_id": str(loc.get("id", "")),
            "name": name,
            # Terra returns floats; Content API returned strings — keep as strings for _find_match compat
            "latitude": str(coords.get("latitude", "")),
            "longitude": str(coords.get("longitude", "")),
            "rating": overall.get("rating"),
            "num_reviews": overall.get("count"),
        }

    # ── Reviews ───────────────────────────────────────────────────────────────

    def _fetch_reviews(self, location_id: str) -> list[str]:
        cache_path = os.path.join(self._cache_dir, f"tripadvisor_review_{location_id}.json")
        cutoff = time.time() - _CACHE_TTL_SECONDS

        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > cutoff:
            with open(cache_path) as f:
                return json.load(f)

        snippets = self._call_reviews(location_id)
        with open(cache_path, "w") as f:
            json.dump(snippets, f)
        return snippets

    def _call_reviews(self, location_id: str) -> list[str]:
        params = {"language": "en", "size": 10}
        try:
            resp = requests.get(
                f"{_API_BASE}/locations/{location_id}/reviews",
                headers=self._headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            snippets = []
            for review in data:
                text_list = review.get("text") or []
                # text is a list of {language, value, primary} objects
                text = next((t["value"] for t in text_list if t.get("primary")), None)
                if not text and text_list:
                    text = text_list[0].get("value")
                if text and len(text) >= _MIN_REVIEW_CHARS:
                    snippets.append(text)
            return snippets[:_MAX_REVIEWS]
        except Exception as exc:
            print(f"[tripadvisor] reviews error for {location_id}: {exc}", flush=True)
            return []

    # ── Photos ────────────────────────────────────────────────────────────────

    def _fetch_photos(self, location_id: str) -> list[str]:
        cache_path = os.path.join(self._cache_dir, f"tripadvisor_photos_{location_id}.json")
        cutoff = time.time() - _CACHE_TTL_SECONDS

        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > cutoff:
            with open(cache_path) as f:
                return json.load(f)

        urls = self._call_photos(location_id)
        with open(cache_path, "w") as f:
            json.dump(urls, f)
        return urls

    def _call_photos(self, location_id: str) -> list[str]:
        params = {"size": _MAX_PHOTOS}
        try:
            resp = requests.get(
                f"{_API_BASE}/locations/{location_id}/photos",
                headers=self._headers,
                params=params,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            urls = []
            for photo in data:
                url = (photo.get("photo") or {}).get("original_size_url")
                if url:
                    urls.append(url)
            return urls[:_MAX_PHOTOS]
        except Exception as exc:
            print(f"[tripadvisor] photos error for {location_id}: {exc}", flush=True)
            return []

    # ── ChromaDB index + match ────────────────────────────────────────────────

    def _build_index(self, pool: list[dict[str, Any]]) -> Any:
        client = chromadb.EphemeralClient()
        collection = client.create_collection(f"ta_merge_{uuid.uuid4().hex}")
        names = [item.get("name", "") for item in pool]
        ids = [str(i) for i in range(len(pool))]
        collection.add(documents=names, ids=ids)
        return collection

    def _find_match(self, poi: POI, pool: list[dict[str, Any]], collection: Any) -> dict[str, Any] | None:
        results = collection.query(query_texts=[poi.name], n_results=1)
        distances = results["distances"][0]
        ids = results["ids"][0]

        if distances and distances[0] <= _SIMILARITY_THRESHOLD:
            return pool[int(ids[0])]

        # Proximity fallback: embedding similarity failed (name divergence), use geography.
        best_km = float("inf")
        best: dict[str, Any] | None = None
        for item in pool:
            try:
                lat = float(item.get("latitude", ""))
                lon = float(item.get("longitude", ""))
            except (TypeError, ValueError):
                continue
            km = _haversine_km(poi.lat, poi.lon, lat, lon)
            if km < best_km:
                best_km = km
                best = item
        return best if best_km <= _PROXIMITY_KM else None

    # ── RatedPOI assembly ─────────────────────────────────────────────────────

    def _make_rated(self, poi: POI, pool: list[dict[str, Any]], collection: Any) -> RatedPOI:
        match = self._find_match(poi, pool, collection)
        if match is None:
            return RatedPOI(poi=poi, review_source=self.source_name)

        location_id = str(match.get("location_id", ""))

        # TripAdvisor rating is already 1–5 — no ÷2 normalization needed
        raw_rating = match.get("rating")
        try:
            rating = float(raw_rating) if raw_rating is not None and raw_rating != "" else None
        except (TypeError, ValueError):
            rating = None

        try:
            review_count = int(match["num_reviews"]) if match.get("num_reviews") is not None else None
        except (TypeError, ValueError):
            review_count = None

        snippets = self._fetch_reviews(location_id) if location_id else []
        photos = self._fetch_photos(location_id) if location_id else []

        return RatedPOI(
            poi=poi,
            rating=rating,
            review_count=review_count,
            review_snippet=snippets[0] if snippets else None,
            all_snippets=snippets if snippets else None,
            review_source=self.source_name,
            photo_urls=photos if photos else None,
        )

    # ── Cache path helpers ────────────────────────────────────────────────────

    def _poi_cache_path(self, poi: POI) -> str:
        safe_id = poi.osm_id.replace("/", "_").replace(" ", "_")
        return os.path.join(self._cache_dir, f"tripadvisor_poi_{safe_id}.json")
