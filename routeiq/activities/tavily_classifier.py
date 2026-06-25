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
            results, cached_names = self._fetch(city, activity)
            if not results:
                continue
            if cached_names is not None:
                matched_names = cached_names
            else:
                matched_names = self._extract_matched_names(results, poi_names, activity)
                self._save_matched_names(city, activity, matched_names)
            snippet = self._top_snippet(results)
            for poi in pois:
                if poi.name in matched_names:
                    classified[poi.osm_id].matched_activities.append(activity)
                    if not classified[poi.osm_id].activity_evidence:
                        classified[poi.osm_id].activity_evidence = f"Tavily: '{snippet}'"

        return list(classified.values())

    # ── Tavily search ──────────────────────────────────────────────────────────

    def _fetch(self, city: str, activity: str) -> tuple[list[dict], list[str] | None]:
        """Returns (raw_results, cached_matched_names_or_None).

        Cache format is {"results": [...], "matched_names": [...]} after first LLM extraction.
        Older cache files are plain lists (raw results only) — read as results with no cached names.
        """
        path = self._cache_path(city, activity)
        if os.path.exists(path) and os.path.getmtime(path) > time.time() - _CACHE_TTL:
            with open(path) as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                return cached.get("results", []), cached.get("matched_names")
            # Legacy format: plain list of results, no cached names yet
            return cached, None
        data = self._call(city, activity)
        with open(path, "w") as f:
            json.dump({"results": data, "matched_names": None}, f)
        return data, None

    def _save_matched_names(self, city: str, activity: str, names: list[str]) -> None:
        path = self._cache_path(city, activity)
        try:
            with open(path) as f:
                cached = json.load(f)
            results = cached.get("results", []) if isinstance(cached, dict) else cached
            with open(path, "w") as f:
                json.dump({"results": results, "matched_names": names}, f)
        except Exception:
            pass

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
        import re
        from langchain_core.messages import HumanMessage
        snippets = "\n".join(
            f"- {r.get('title', '')}: {r.get('content', '')[:200]}" for r in results[:8]
        )
        # Send all POI names so well-known places (e.g. "Golden Gate Bridge" at index 420)
        # are visible to the LLM, not just the first 40.
        names_str = "\n".join(poi_names)
        prompt = (
            f"Web search results for '{activity}':\n{snippets}\n\n"
            f"From this POI list, which names appear or are strongly implied in the results above?\n"
            f"{names_str}\n\n"
            f"Return a JSON array of matched names only. No explanation."
        )
        try:
            response = self._llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip()
            # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw).strip()
            result = json.loads(raw)
            return result if isinstance(result, list) else []
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
