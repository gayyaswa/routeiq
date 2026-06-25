from __future__ import annotations
import json
import os
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from routeiq.graph.poi import POI
from routeiq.ratings.base import POIRatingProvider, RatedPOI

_CACHE_DIR = "./cache/ratings"
_CACHE_TTL_SECONDS = 21 * 86400

_SYSTEM = """You are a travel data generator. Given a list of points of interest,
produce realistic visitor ratings and review snippets that a traveler would write after visiting.

Rules:
- Ratings range 3.8–4.9. Well-known landmarks trend 4.5+; smaller/niche spots trend 3.9–4.3.
- review_count: plausible visitor volume. Famous sites: 1000–15000. Local gems: 80–600.
- snippets: 2–3 review texts, each 60–140 chars, first-person present/past tense. Vary tone.
- hours: realistic opening hours string, e.g. "Daily 9:00 AM – 5:00 PM" or "Tue–Sun 10:00 AM – 4:00 PM". Use None if unknown.
- Ground ratings and reviews in the description when provided; invent plausibly when not.

Respond with ONLY a JSON array. Each element must have exactly these keys:
  name (string), rating (float), review_count (int), snippets (array of strings), hours (string or null)

No markdown, no prose. Just the JSON array."""


class LLMSyntheticRatingProvider(POIRatingProvider):
    """Generates synthetic ratings and reviews via LLM when live APIs are unavailable (Strategy pattern)."""

    @property
    def source_name(self) -> str:
        return "AI Insights"

    def __init__(self, cache_dir: str = _CACHE_DIR):
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._llm = None  # lazy-loaded to avoid import overhead when not used

    def _get_llm(self):
        if self._llm is None:
            from routeiq.llm_factory import create_llm
            self._llm = create_llm()
        return self._llm

    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        if not pois:
            return []

        cache_path = self._cache_path(city)
        pool = self._load_or_generate(city, pois, cache_path)

        index: dict[str, dict[str, Any]] = {item["name"]: item for item in pool}
        results = []
        for poi in pois:
            match = index.get(poi.name)
            if match is None:
                results.append(RatedPOI(poi=poi, review_source=self.source_name))
                continue

            snippets = match.get("snippets") or []
            results.append(RatedPOI(
                poi=poi,
                rating=match.get("rating"),
                review_count=match.get("review_count"),
                review_snippet=snippets[0] if snippets else None,
                all_snippets=snippets or None,
                review_source=self.source_name,
                hours=match.get("hours"),
            ))
        return results

    def _load_or_generate(self, city: str, pois: list[POI], cache_path: str) -> list[dict[str, Any]]:
        cutoff = time.time() - _CACHE_TTL_SECONDS
        if os.path.exists(cache_path) and os.path.getmtime(cache_path) > cutoff:
            try:
                with open(cache_path) as f:
                    cached: list[dict] = json.load(f)
                cached_names = {item["name"] for item in cached}
                missing = [p for p in pois if p.name not in cached_names]
                if not missing:
                    return cached
                # Generate only the missing POIs and merge
                new_items = self._call_llm(city, missing)
                merged = cached + new_items
                with open(cache_path, "w") as f:
                    json.dump(merged, f)
                return merged
            except Exception:
                pass

        items = self._call_llm(city, pois)
        try:
            with open(cache_path, "w") as f:
                json.dump(items, f)
        except Exception:
            pass
        return items

    # 50 POIs × ~120 chars each ≈ 6K tokens per batch; 900-POI single call caused context overflow.
    _BATCH_SIZE = 50

    def _call_llm(self, city: str, pois: list[POI]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for i in range(0, len(pois), self._BATCH_SIZE):
            results.extend(self._call_llm_single(city, pois[i:i + self._BATCH_SIZE]))
        return results

    def _call_llm_single(self, city: str, pois: list[POI]) -> list[dict[str, Any]]:
        poi_entries = []
        for p in pois:
            entry: dict[str, Any] = {"name": p.name, "category": p.category}
            if p.subtype:
                entry["subtype"] = p.subtype
            if p.description:
                entry["description"] = p.description[:300]
            poi_entries.append(entry)

        user_msg = (
            f"City: {city}\n\n"
            f"Generate ratings and reviews for these {len(pois)} points of interest:\n\n"
            + json.dumps(poi_entries, ensure_ascii=False)
        )

        try:
            llm = self._get_llm()
            response = llm.invoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=user_msg),
            ])
            text = response.content.strip()
            # Strip markdown fences if the LLM wraps output despite instruction
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.rsplit("```", 1)[0].strip()
            parsed: list[dict] = json.loads(text)
            return parsed
        except Exception as exc:
            print(f"[llm_synthetic] generation failed: {exc}", flush=True)
            return []

    def _cache_path(self, city: str) -> str:
        safe_city = city.replace(" ", "_").replace(",", "").lower()
        return os.path.join(self._cache_dir, f"llm_synthetic_{safe_city}.json")
