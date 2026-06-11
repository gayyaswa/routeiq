"""Fetches Wikipedia summary text and thumbnail URL for POI enrichment (Strategy pattern)."""
from __future__ import annotations

import requests

from routeiq.graph.poi import POI

_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_DESCRIPTION_MAX_CHARS = 500
_REQUEST_TIMEOUT = 15  # Wikipedia API can respond slowly; 5s caused silent enrichment failures


class WikipediaFetcher:
    """Enriches POI objects with Wikipedia text extract and thumbnail URL (Strategy pattern)."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def enrich(self, poi: POI) -> None:
        """Mutates poi in-place: sets description and image_url from Wikipedia."""
        title = self._resolve_title(poi)
        if not title:
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

    def _resolve_title(self, poi: POI) -> str | None:
        """Returns Wikipedia article title from OSM tag or name-based search fallback."""
        if poi.wikipedia_tag:
            # OSM tag format: "en:Title" or plain "Title"
            tag = poi.wikipedia_tag
            return tag.split(":", 1)[-1] if ":" in tag else tag

        # name-based fallback via MediaWiki opensearch.
        # Appending "California" dramatically improves disambiguation — bare POI names
        # like "Lighthouse" or "Adobe" resolve to generic articles with empty extracts.
        try:
            resp = self._session.get(
                _SEARCH_URL,
                params={
                    "action": "opensearch",
                    "search": f"{poi.name} California",
                    "limit": 1,
                    "namespace": 0,
                    "format": "json",
                },
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return None
            results = resp.json()
            # opensearch returns [query, [titles], [descriptions], [urls]]
            titles = results[1] if len(results) > 1 else []
            return titles[0] if titles else None
        except Exception:
            return None
