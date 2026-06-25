"""Fetches Wikipedia summary text and thumbnail URL for POI enrichment (Strategy pattern)."""
from __future__ import annotations

import json
import os
import threading

import requests

from routeiq.graph.poi import POI

_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_DESCRIPTION_MAX_CHARS = 500
_REQUEST_TIMEOUT = 15  # Wikipedia API can respond slowly; 5s caused silent enrichment failures

# TODO: unify with llm_synthetic.py and tavily_classifier.py into a shared CacheLayer.
# All three follow the same pattern: JSON file, TTL optional, keyed by a string identifier.
_CACHE_PATH = "./cache/wikipedia/descriptions.json"
_cache_lock = threading.Lock()
_cache: dict[str, dict] | None = None  # {poi_name: {description, image_url}}


def _load_cache() -> dict[str, dict]:
    global _cache
    if _cache is not None:
        return _cache
    with _cache_lock:
        if _cache is not None:
            return _cache
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        try:
            with open(_CACHE_PATH) as f:
                _cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _cache = {}
    return _cache


def _write_cache(cache: dict) -> None:
    try:
        with open(_CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


class WikipediaFetcher:
    """Enriches POI objects with Wikipedia text extract and thumbnail URL (Strategy pattern)."""

    # Wikipedia API policy requires a descriptive User-Agent or requests return 403.
    _USER_AGENT = "RouteIQ/1.0 (scenic route assistant; guruplace04@gmail.com)"

    def __init__(self, session: requests.Session | None = None) -> None:
        if session is None:
            session = requests.Session()
            session.headers.update({"User-Agent": self._USER_AGENT})
        self._session = session

    def enrich(self, poi: POI) -> None:
        """Mutates poi in-place: sets description and image_url from Wikipedia."""
        cache = _load_cache()
        hit = cache.get(poi.name)
        if hit is not None:
            poi.description = hit.get("description") or poi.description
            poi.image_url = hit.get("image_url") or poi.image_url
            return

        title = self._resolve_title(poi)
        if not title:
            # Cache the miss so we don't retry on every refinement run
            with _cache_lock:
                cache[poi.name] = {"description": None, "image_url": None}
            _write_cache(cache)
            return

        try:
            resp = self._session.get(
                _SUMMARY_URL.format(title=requests.utils.quote(title, safe="")),
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return
            data = resp.json()
            extract = data.get("extract", "")
            if extract:
                poi.description = extract[:_DESCRIPTION_MAX_CHARS]
            thumb = data.get("thumbnail") or {}
            if thumb.get("source"):
                poi.image_url = thumb["source"]
            # Fallback: REST summary only returns free-license thumbnails.
            # pageimages with pilicense=any also returns non-free images used
            # under fair use — common for historic sites and tourism landmarks.
            if not poi.image_url:
                img_resp = self._session.get(
                    _SEARCH_URL,
                    params={
                        "action": "query",
                        "titles": title,
                        "prop": "pageimages",
                        "format": "json",
                        "pithumbsize": 300,
                        "pilicense": "any",
                    },
                    timeout=_REQUEST_TIMEOUT,
                )
                if img_resp.status_code == 200:
                    pages = img_resp.json().get("query", {}).get("pages", {})
                    for page in pages.values():
                        src = page.get("thumbnail", {}).get("source")
                        if src:
                            poi.image_url = src
                            break
        except Exception:
            pass  # graceful degradation — narrative falls back to name + category

        with _cache_lock:
            cache[poi.name] = {
                "description": poi.description,
                "image_url": poi.image_url,
            }
        _write_cache(cache)

    def _resolve_title(self, poi: POI) -> str | None:
        """Returns Wikipedia article title from OSM tag or name-based search fallback."""
        if poi.wikipedia_tag:
            # OSM tag format: "en:Title" or plain "Title"
            tag = poi.wikipedia_tag
            return tag.split(":", 1)[-1] if ":" in tag else tag

        # name-based fallback via MediaWiki opensearch.
        # Try exact name first — specific names like "Pigeon Point Lighthouse" match directly.
        # Fall back to "<name> California" for generic names that need geo-disambiguation
        # (e.g., "Lighthouse" or "Adobe" would otherwise resolve to unrelated articles).
        for query in [poi.name, f"{poi.name} California"]:
            try:
                resp = self._session.get(
                    _SEARCH_URL,
                    params={
                        "action": "opensearch",
                        "search": query,
                        "limit": 1,
                        "namespace": 0,
                        "format": "json",
                    },
                    timeout=_REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    continue
                results = resp.json()
                titles = results[1] if len(results) > 1 else []
                if titles:
                    return titles[0]
            except Exception:
                continue
        return None
