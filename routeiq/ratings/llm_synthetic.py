from __future__ import annotations
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from routeiq.graph.poi import POI
from routeiq.ratings.base import POIRatingProvider, RatedPOI

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
    """Generates synthetic ratings and reviews via LLM when live APIs are unavailable (Strategy pattern).

    Caching is handled upstream by POIRatingStore (ChromaDB, 21-day TTL) and the
    in-session poi_cache in DayTripState — this class is a pure fetch-and-return.
    """

    # 50 POIs × ~120 chars each ≈ 6K tokens per batch; single call for 900 POIs caused overflow.
    _BATCH_SIZE = 50

    @property
    def source_name(self) -> str:
        return "AI Insights"

    def __init__(self) -> None:
        self._llm = None  # lazy-loaded

    def _get_llm(self):
        if self._llm is None:
            from routeiq.llm_factory import create_llm
            self._llm = create_llm()
        return self._llm

    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        if not pois:
            return []
        items = self._call_llm(city, pois)
        index: dict[str, dict[str, Any]] = {item["name"]: item for item in items}
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
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.rsplit("```", 1)[0].strip()
            return json.loads(text)
        except Exception as exc:
            print(f"[llm_synthetic] generation failed: {exc}", flush=True)
            return []
