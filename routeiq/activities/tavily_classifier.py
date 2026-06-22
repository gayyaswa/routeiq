from __future__ import annotations
import json
import os
import time

from routeiq.graph.poi import POI
from routeiq.activities.base import ActivityClassifier, ClassifiedPOI

_CACHE_DIR = "./cache/activities"
_CACHE_TTL = 21 * 86400


class TavilyActivityClassifier(ActivityClassifier):
    """Classifies POI activities via Tavily web search — bulk fetch per (city, activity)."""

    def __init__(self, api_key: str, llm, cache_dir: str = _CACHE_DIR):
        from tavily import TavilyClient
        self._client = TavilyClient(api_key=api_key)
        self._llm = llm
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def classify_batch(
        self, city: str, pois: list[POI], activities: list[str]
    ) -> list[ClassifiedPOI]:
        classified: dict[str, ClassifiedPOI] = {p.osm_id: ClassifiedPOI(poi=p) for p in pois}
        poi_names = [p.name for p in pois]

        for activity in activities:
            results = self._fetch(city, activity)
            if not results:
                continue
            matched_names = self._extract_matched_names(results, poi_names, activity)
            snippet = self._top_snippet(results)
            for poi in pois:
                if poi.name in matched_names:
                    classified[poi.osm_id].matched_activities.append(activity)
                    if not classified[poi.osm_id].activity_evidence:
                        classified[poi.osm_id].activity_evidence = f"Tavily: '{snippet}'"

        return list(classified.values())

    # ── Tavily search ──────────────────────────────────────────────────────────

    def _fetch(self, city: str, activity: str) -> list[dict]:
        path = self._cache_path(city, activity)
        if os.path.exists(path) and os.path.getmtime(path) > time.time() - _CACHE_TTL:
            with open(path) as f:
                return json.load(f)
        data = self._call(city, activity)
        with open(path, "w") as f:
            json.dump(data, f)
        return data

    def _call(self, city: str, activity: str) -> list[dict]:
        try:
            resp = self._client.search(
                query=f"{activity} places to visit in {city}",
                max_results=10,
                include_answer=False,
            )
            return resp.get("results", [])
        except Exception as e:
            print(f"[tavily_classifier] search error: {e}", flush=True)
            return []

    # ── LLM name extraction ────────────────────────────────────────────────────

    def _extract_matched_names(
        self, results: list[dict], poi_names: list[str], activity: str
    ) -> list[str]:
        from langchain_core.messages import HumanMessage
        snippets = "\n".join(
            f"- {r.get('title', '')}: {r.get('content', '')[:200]}" for r in results[:8]
        )
        names_str = "\n".join(poi_names[:40])
        prompt = (
            f"Web search results for '{activity}':\n{snippets}\n\n"
            f"From this POI list, which names appear or are strongly implied in the results above?\n"
            f"{names_str}\n\n"
            f"Return a JSON array of matched names only. No explanation."
        )
        try:
            response = self._llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip().strip("```json").strip("```").strip()
            return json.loads(raw)
        except Exception:
            return []

    def _top_snippet(self, results: list[dict]) -> str:
        for r in results:
            content = r.get("content", "")
            if len(content) > 40:
                return content[:120]
        return ""

    def _cache_path(self, city: str, activity: str) -> str:
        def safe(s):
            return s.lower().replace(" ", "_").replace(",", "")
        return os.path.join(self._cache_dir, f"tavily_classify_{safe(city)}_{safe(activity)}.json")
