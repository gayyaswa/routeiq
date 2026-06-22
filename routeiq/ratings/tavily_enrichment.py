from __future__ import annotations
import json
import os
import time

from routeiq.graph.poi import POI
from routeiq.ratings.base import POIRatingProvider, RatedPOI

_CACHE_DIR = "./cache/ratings"
_CACHE_TTL = 21 * 86400


class TavilyEnrichmentProvider(POIRatingProvider):
    """Enriches POIs with real web-sourced highlights, quotes, and photos (Strategy pattern)."""

    def __init__(self, api_key: str, llm, cache_dir: str = _CACHE_DIR):
        from tavily import TavilyClient
        self._client = TavilyClient(api_key=api_key)
        self._llm = llm
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    @property
    def source_name(self) -> str:
        return "Tavily"

    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        if not pois:
            return []
        bulk_results = self._bulk_fetch(city)
        return [self._make_rated(poi, city, bulk_results) for poi in pois]

    # ── Bulk search ────────────────────────────────────────────────────────────

    def _bulk_fetch(self, city: str) -> list[dict]:
        safe = city.lower().replace(" ", "_").replace(",", "")
        path = os.path.join(self._cache_dir, f"tavily_enrich_{safe}.json")
        if os.path.exists(path) and os.path.getmtime(path) > time.time() - _CACHE_TTL:
            with open(path) as f:
                return json.load(f)
        try:
            resp = self._client.search(
                query=f"best visitor highlights reviews attractions {city}",
                max_results=15,
                include_answer=False,
            )
            data = resp.get("results", [])
        except Exception as e:
            print(f"[tavily_enrich] bulk search error: {e}", flush=True)
            data = []
        with open(path, "w") as f:
            json.dump(data, f)
        return data

    def _poi_fetch(self, poi: POI, city: str) -> list[dict]:
        safe_id = poi.osm_id.replace("/", "_")
        path = os.path.join(self._cache_dir, f"tavily_enrich_poi_{safe_id}.json")
        if os.path.exists(path) and os.path.getmtime(path) > time.time() - _CACHE_TTL:
            with open(path) as f:
                return json.load(f)
        try:
            resp = self._client.search(
                query=f"{poi.name} {city} visitor experience reviews",
                max_results=5,
                include_answer=False,
            )
            data = resp.get("results", [])
        except Exception as e:
            print(f"[tavily_enrich] poi search error for {poi.name}: {e}", flush=True)
            data = []
        with open(path, "w") as f:
            json.dump(data, f)
        return data

    # ── RatedPOI assembly ──────────────────────────────────────────────────────

    def _make_rated(self, poi: POI, city: str, bulk_results: list[dict]) -> RatedPOI:
        poi_lower = poi.name.lower()
        relevant = [
            r for r in bulk_results
            if poi_lower in (r.get("content", "") + r.get("title", "")).lower()
        ]
        if len(relevant) < 2:
            relevant = self._poi_fetch(poi, city)
        if not relevant:
            return RatedPOI(poi=poi, review_source=self.source_name)

        signals = self._extract_signals(poi, relevant)
        photo_url = next(
            (r.get("url") for r in relevant
             if r.get("url", "").endswith((".jpg", ".jpeg", ".png", ".webp"))),
            None,
        )
        return RatedPOI(
            poi=poi,
            review_source=self.source_name,
            review_snippet=signals.get("visitor_quote"),
            all_snippets=signals.get("highlights", []),
            photo_urls=[photo_url] if photo_url else None,
        )

    def _extract_signals(self, poi: POI, results: list[dict]) -> dict:
        from langchain_core.messages import HumanMessage
        snippets = "\n".join(
            f"- {r.get('title', '')}: {r.get('content', '')[:300]}" for r in results[:5]
        )
        prompt = (
            f"Web results about {poi.name}:\n{snippets}\n\n"
            f"Extract:\n"
            f"1. visitor_quote: best single quote (max 20 words)\n"
            f"2. highlights: 3 specific things visitors mention (short bullets)\n"
            f"Return JSON only: {{\"visitor_quote\": \"...\", \"highlights\": [\"...\", \"...\", \"...\"]}}"
        )
        try:
            resp = self._llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip().strip("```json").strip("```").strip()
            return json.loads(raw)
        except Exception:
            return {}
