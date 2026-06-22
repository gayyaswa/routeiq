# Detailed Implementation Plan — Activity-Based Day Trip Planning

Design docs: `architecture.md`, `data-flows.md`, `activity-planning-spec.md`
Build in the order below — each step has a verify check before moving on.

---

## Step 0 — Data model (no behavior, no tests fail)

### `routeiq/ratings/base.py` — add 2 fields to `RatedPOI`

```python
# Add to existing RatedPOI dataclass after existing fields:
matched_activities: list[str] | None = None   # carried from ActivityClassifier
activity_evidence: str | None = None           # grounded source: "Tavily: 'coastal trail'"
```

### NEW `routeiq/activities/__init__.py`

```python
from routeiq.activities.base import ActivityClassifier, ClassifiedPOI
from routeiq.activities.factory import create_activity_classifier, create_ranker
```

### NEW `routeiq/activities/base.py`

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from routeiq.graph.poi import POI

@dataclass
class ClassifiedPOI:
    poi: POI
    matched_activities: list[str] = field(default_factory=list)
    activity_evidence: str | None = None    # top snippet from classifier source
    activity_rank_score: float = 0.0        # set by ActivityRanker; 0 = unranked

class ActivityClassifier(ABC):
    """Classifies which activities are supported at each POI (Strategy pattern)."""
    @abstractmethod
    def classify_batch(
        self,
        city: str,
        pois: list[POI],
        activities: list[str],
    ) -> list[ClassifiedPOI]:
        """Return every input POI as ClassifiedPOI; unmatched get matched_activities=[]."""
        ...
```

**Verify:** `python3 -c "from routeiq.activities import ActivityClassifier, ClassifiedPOI; print('OK')`

---

## Step 1 — `OSMActivityClassifier` (free baseline, zero API calls)

### NEW `routeiq/activities/osm_classifier.py`

```python
from __future__ import annotations
from routeiq.graph.poi import POI
from routeiq.activities.base import ActivityClassifier, ClassifiedPOI

# OSM tag value → activity label. Extend as needed.
_TAG_TO_ACTIVITY: dict[str, str] = {
    "cycling_path":     "biking",
    "track":            "biking",
    "peak":             "hiking",
    "nature_reserve":   "hiking",
    "cliff":            "hiking",
    "playground":       "kids",
    "theme_park":       "kids",
    "zoo":              "kids",
    "swimming_pool":    "swimming",
    "beach":            "swimming",
    "water_park":       "swimming",
    "kayaking":         "kayaking",
    "marina":           "kayaking",
    "picnic_site":      "picnic",
    "garden":           "picnic",
}

# Also check poi.category prefix directly (e.g. "leisure=cycling_path" → "cycling_path")
_CATEGORY_KEYWORDS: dict[str, str] = {
    "bike":    "biking",
    "cycl":    "biking",
    "trail":   "hiking",
    "hike":    "hiking",
    "climb":   "hiking",
    "child":   "kids",
    "family":  "kids",
    "play":    "kids",
    "swim":    "swimming",
    "beach":   "swimming",
    "kayak":   "kayaking",
    "canoe":   "kayaking",
    "picnic":  "picnic",
}

class OSMActivityClassifier(ActivityClassifier):
    """Classifies activities from OSM tags already present on POI objects (Registry pattern)."""

    def classify_batch(
        self,
        city: str,
        pois: list[POI],
        activities: list[str],
    ) -> list[ClassifiedPOI]:
        result = []
        activity_set = set(a.lower() for a in activities)

        for poi in pois:
            matched = self._match(poi, activity_set)
            result.append(ClassifiedPOI(
                poi=poi,
                matched_activities=matched,
                activity_evidence=f"OSM tag: {poi.category}" if matched else None,
            ))
        return result

    def _match(self, poi: POI, activity_set: set[str]) -> list[str]:
        matched = []
        cat = (poi.category or "").lower()

        # Check full tag map first
        for tag_val, activity in _TAG_TO_ACTIVITY.items():
            if activity in activity_set and tag_val in cat:
                matched.append(activity)

        # Keyword fallback on category string
        for keyword, activity in _CATEGORY_KEYWORDS.items():
            if activity in activity_set and keyword in cat and activity not in matched:
                matched.append(activity)

        return list(set(matched))
```

**Verify:**
```bash
python3 -c "
from routeiq.activities.osm_classifier import OSMActivityClassifier
from routeiq.graph.poi import POI
c = OSMActivityClassifier()
pois = [POI(id='1', name='Test Trail', lat=0, lon=0, category='leisure=cycling_path', scenic_score=0.5)]
result = c.classify_batch('TestCity', pois, ['biking'])
print(result[0].matched_activities)  # should print ['biking']
"
```

---

## Step 2 — `TavilyActivityClassifier`

### NEW `routeiq/activities/tavily_classifier.py`

```python
from __future__ import annotations
import json, os, time
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
        # Build a mutable result dict keyed by poi.id
        classified: dict[str, ClassifiedPOI] = {
            p.id: ClassifiedPOI(poi=p) for p in pois
        }
        poi_names = [p.name for p in pois]

        for activity in activities:
            results = self._fetch(city, activity)
            if not results:
                continue
            matched_names = self._extract_matched_names(results, poi_names, activity)
            snippet = self._top_snippet(results)
            for poi in pois:
                if poi.name in matched_names:
                    classified[poi.id].matched_activities.append(activity)
                    if not classified[poi.id].activity_evidence:
                        classified[poi.id].activity_evidence = f"Tavily: '{snippet}'"

        return list(classified.values())

    # ── Tavily search ─────────────────────────────────────────────────────────

    def _fetch(self, city: str, activity: str) -> list[dict]:
        path = self._cache_path(city, activity)
        cutoff = time.time() - _CACHE_TTL
        if os.path.exists(path) and os.path.getmtime(path) > cutoff:
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

    # ── LLM extraction ────────────────────────────────────────────────────────

    def _extract_matched_names(
        self, results: list[dict], poi_names: list[str], activity: str
    ) -> list[str]:
        from langchain_core.messages import HumanMessage
        snippets = "\n".join(
            f"- {r.get('title','')}: {r.get('content','')[:200]}" for r in results[:8]
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
        safe = lambda s: s.lower().replace(" ", "_").replace(",", "")
        return os.path.join(self._cache_dir, f"tavily_classify_{safe(city)}_{safe(activity)}.json")
```

**Verify (mocked):** `python3 -m pytest tests/test_tavily_classifier.py -v`

---

## Step 3 — `PerplexityActivityClassifier`

### NEW `routeiq/activities/perplexity_classifier.py`

```python
from __future__ import annotations
import json, os, time
import requests
from routeiq.graph.poi import POI
from routeiq.activities.base import ActivityClassifier, ClassifiedPOI

_CACHE_DIR = "./cache/activities"
_CACHE_TTL = 21 * 86400
_API_URL = "https://api.perplexity.ai/chat/completions"

class PerplexityActivityClassifier(ActivityClassifier):
    """Classifies POI activities via Perplexity AI — one synthesized query per city."""

    def __init__(self, api_key: str, llm, cache_dir: str = _CACHE_DIR):
        self._api_key = api_key
        self._llm = llm
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def classify_batch(
        self, city: str, pois: list[POI], activities: list[str]
    ) -> list[ClassifiedPOI]:
        classified: dict[str, ClassifiedPOI] = {
            p.id: ClassifiedPOI(poi=p) for p in pois
        }

        answer = self._fetch(city, activities)
        if not answer:
            return list(classified.values())

        pairs = self._parse_pairs(answer, pois, activities)
        for poi_id, acts in pairs.items():
            if poi_id in classified:
                classified[poi_id].matched_activities = acts
                classified[poi_id].activity_evidence = f"Perplexity (cited)"

        return list(classified.values())

    # ── Perplexity call ───────────────────────────────────────────────────────

    def _fetch(self, city: str, activities: list[str]) -> str:
        key = "_".join(sorted(activities))
        safe = lambda s: s.lower().replace(" ", "_").replace(",", "")
        path = os.path.join(self._cache_dir, f"perplexity_{safe(city)}_{safe(key)}.json")
        cutoff = time.time() - _CACHE_TTL

        if os.path.exists(path) and os.path.getmtime(path) > cutoff:
            with open(path) as f:
                return json.load(f)

        answer = self._call(city, activities)
        with open(path, "w") as f:
            json.dump(answer, f)
        return answer

    def _call(self, city: str, activities: list[str]) -> str:
        acts_str = ", ".join(activities)
        payload = {
            "model": "llama-3.1-sonar-large-128k-online",
            "messages": [
                {"role": "system", "content": "You are a travel expert. Be specific and cite sources."},
                {"role": "user", "content": (
                    f"In {city}, which specific venues, parks, or attractions are well-known for: {acts_str}?\n"
                    f"For each venue, state which of these activities apply.\n"
                    f"Format: venue name | activity1, activity2"
                )},
            ],
        }
        try:
            resp = requests.post(
                _API_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[perplexity_classifier] error: {e}", flush=True)
            return ""

    # ── Parse venue|activity lines + match to POIs ────────────────────────────

    def _parse_pairs(
        self, answer: str, pois: list[POI], activities: list[str]
    ) -> dict[str, list[str]]:
        from langchain_core.messages import HumanMessage
        poi_names = [p.name for p in pois]
        activity_set = set(a.lower() for a in activities)
        prompt = (
            f"Perplexity answer:\n{answer}\n\n"
            f"POI list:\n" + "\n".join(poi_names[:40]) + "\n\n"
            f"Valid activities: {list(activity_set)}\n\n"
            f"Return JSON: {{\"poi_name\": [\"activity1\", ...], ...}} "
            f"Only include POIs from the list. Only include valid activities."
        )
        try:
            resp = self._llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip().strip("```json").strip("```").strip()
            name_to_acts: dict[str, list[str]] = json.loads(raw)
            # Map name → poi.id
            name_to_id = {p.name: p.id for p in pois}
            return {name_to_id[n]: acts for n, acts in name_to_acts.items() if n in name_to_id}
        except Exception:
            return {}
```

**Verify (mocked):** `python3 -m pytest tests/test_perplexity_classifier.py -v`

---

## Step 4 — `TavilyEnrichmentProvider` (Tavily as `POIRatingProvider`)

### NEW `routeiq/ratings/tavily_enrichment.py`

```python
from __future__ import annotations
import json, os, time
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

    # ── Bulk search ───────────────────────────────────────────────────────────

    def _bulk_fetch(self, city: str) -> list[dict]:
        safe = city.lower().replace(" ", "_").replace(",", "")
        path = os.path.join(self._cache_dir, f"tavily_enrich_{safe}.json")
        cutoff = time.time() - _CACHE_TTL

        if os.path.exists(path) and os.path.getmtime(path) > cutoff:
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
        safe = poi.id.replace("/", "_")
        path = os.path.join(self._cache_dir, f"tavily_enrich_poi_{safe}.json")
        cutoff = time.time() - _CACHE_TTL

        if os.path.exists(path) and os.path.getmtime(path) > cutoff:
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

    # ── RatedPOI assembly ─────────────────────────────────────────────────────

    def _make_rated(self, poi: POI, city: str, bulk_results: list[dict]) -> RatedPOI:
        relevant = [r for r in bulk_results if poi.name.lower() in (r.get("content","") + r.get("title","")).lower()]
        if len(relevant) < 2:
            relevant = self._poi_fetch(poi, city)
        if not relevant:
            return RatedPOI(poi=poi, review_source=self.source_name)

        signals = self._extract_signals(poi, relevant)
        photo_url = next((r.get("url") for r in relevant if r.get("url","").endswith((".jpg",".jpeg",".png",".webp"))), None)

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
            f"- {r.get('title','')}: {r.get('content','')[:300]}" for r in results[:5]
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
```

Register in `routeiq/ratings/factory.py`:
```python
if provider == "tavily_enrichment":
    from routeiq.ratings.tavily_enrichment import TavilyEnrichmentProvider
    llm = kwargs.get("llm") or create_llm()
    return TavilyEnrichmentProvider(api_key=os.getenv("TAVILY_API_KEY"), llm=llm)
```

---

## Step 5 — `ActivityRanker`

### NEW `routeiq/activities/ranker.py`

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from routeiq.activities.base import ClassifiedPOI

class ActivityRanker(ABC):
    """Ranks ClassifiedPOI candidates for a single activity slot (Strategy pattern)."""
    @abstractmethod
    def rank(
        self,
        candidates: list[ClassifiedPOI],
        activity: str,
        user_context: str,
        ratings: dict[str, float],          # poi_id → 1–5 rating; empty if not yet enriched
    ) -> list[ClassifiedPOI]:
        """Return candidates sorted best-first. Sets activity_rank_score on each."""
        ...


class RatingRanker(ActivityRanker):
    """Ranks by available rating descending; unrated POIs go last."""

    def rank(self, candidates, activity, user_context, ratings):
        def score(c):
            r = ratings.get(c.poi.id, 0.0) or 0.0
            c.activity_rank_score = r / 5.0
            return r
        return sorted(candidates, key=score, reverse=True)


class SemanticRanker(ActivityRanker):
    """Ranks by cosine similarity between user_context and activity_evidence text."""

    def rank(self, candidates, activity, user_context, ratings):
        import chromadb
        from uuid import uuid4
        if not candidates:
            return candidates

        client = chromadb.EphemeralClient()
        col = client.create_collection(f"rank_{uuid4().hex}")

        docs = [c.activity_evidence or c.poi.name for c in candidates]
        ids  = [str(i) for i in range(len(candidates))]
        col.add(documents=docs, ids=ids)

        results = col.query(query_texts=[f"{activity} {user_context}"], n_results=len(candidates))
        distances = results["distances"][0]
        order = results["ids"][0]

        # Lower distance = better match; invert to score
        max_d = max(distances) + 1e-6
        id_to_score = {ids[int(oid)]: 1.0 - (distances[i] / max_d) for i, oid in enumerate(order)}

        for c in candidates:
            idx = ids[candidates.index(c)]
            base = id_to_score.get(idx, 0.0)
            rating_bonus = (ratings.get(c.poi.id, 0.0) or 0.0) / 5.0 * 0.4
            c.activity_rank_score = round(base * 0.6 + rating_bonus, 4)

        return sorted(candidates, key=lambda c: c.activity_rank_score, reverse=True)


class LLMRanker(ActivityRanker):
    """Asks the LLM to rank candidates given full user context."""

    def __init__(self, llm):
        self._llm = llm

    def rank(self, candidates, activity, user_context, ratings):
        import json
        from langchain_core.messages import HumanMessage
        if not candidates:
            return candidates

        lines = "\n".join(
            f"{i}. {c.poi.name}: {c.activity_evidence or 'no evidence'}"
            for i, c in enumerate(candidates)
        )
        prompt = (
            f"User wants: '{user_context}' (activity: {activity})\n\n"
            f"Rank these candidates best to worst:\n{lines}\n\n"
            f"Return JSON array of indices in ranked order, e.g. [2, 0, 1]"
        )
        try:
            resp = self._llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip().strip("```json").strip("```").strip()
            order = json.loads(raw)
            ranked = [candidates[i] for i in order if 0 <= i < len(candidates)]
            for score, c in enumerate(reversed(ranked)):
                c.activity_rank_score = round(score / len(ranked), 4)
            return ranked
        except Exception:
            return candidates   # fallback: return unranked


_DESCRIPTION_ADJECTIVES = {
    "scenic", "coastal", "challenging", "easy", "hidden", "quiet", "family",
    "kid", "historic", "waterfront", "mountain", "forest", "urban",
}

def create_ranker(user_context: str, ratings_available: bool = False, llm=None) -> ActivityRanker:
    words = set(user_context.lower().split())
    if words & _DESCRIPTION_ADJECTIVES:
        return SemanticRanker()
    if ratings_available:
        return RatingRanker()
    if llm:
        return LLMRanker(llm)
    return RatingRanker()
```

---

## Step 6 — `POISelector` (two-track merge)

### NEW `routeiq/routing/poi_selector.py`

```python
from __future__ import annotations
from routeiq.activities.base import ClassifiedPOI
from routeiq.activities.ranker import ActivityRanker, create_ranker

class POISelector:
    """Merges activity-matched (Track 1) and scenic-fill (Track 2) POIs into an itinerary."""

    def select(
        self,
        classified_pois: list[ClassifiedPOI],
        requested_activities: list[str],
        user_context: str = "",
        ratings: dict[str, float] | None = None,
        total_stops: int = 5,
        ranker: ActivityRanker | None = None,
    ) -> list[ClassifiedPOI]:
        ratings = ratings or {}
        n_activity_slots = min(len(requested_activities), 3) if requested_activities else 0
        n_scenic_slots = total_stops - n_activity_slots

        track1 = self._build_track1(
            classified_pois, requested_activities, n_activity_slots,
            user_context, ratings, ranker,
        )
        used_ids = {c.poi.id for c in track1}
        track2 = self._build_track2(classified_pois, used_ids, n_scenic_slots)

        return self._order_by_geography(track1 + track2)

    def _build_track1(
        self,
        classified_pois, requested_activities, n_slots,
        user_context, ratings, ranker,
    ) -> list[ClassifiedPOI]:
        if not requested_activities or n_slots == 0:
            return []

        selected = []
        covered_activities: set[str] = set()

        for activity in requested_activities:
            if len(selected) >= n_slots:
                break
            candidates = [
                c for c in classified_pois
                if activity in c.matched_activities
                and c.poi.id not in {s.poi.id for s in selected}
            ]
            if not candidates:
                continue

            active_ranker = ranker or create_ranker(user_context, bool(ratings))
            ranked = active_ranker.rank(candidates, activity, user_context, ratings)
            if ranked:
                selected.append(ranked[0])
                covered_activities.add(activity)

        return selected

    def _build_track2(
        self, classified_pois, used_ids: set[str], n_slots: int
    ) -> list[ClassifiedPOI]:
        remaining = [c for c in classified_pois if c.poi.id not in used_ids]
        remaining.sort(key=lambda c: c.poi.scenic_score, reverse=True)
        return remaining[:n_slots]

    def _order_by_geography(self, stops: list[ClassifiedPOI]) -> list[ClassifiedPOI]:
        if len(stops) <= 2:
            return stops
        # Nearest-neighbor ordering starting from northernmost POI
        unvisited = list(stops)
        ordered = [min(unvisited, key=lambda c: -c.poi.lat)]
        unvisited.remove(ordered[0])
        while unvisited:
            last = ordered[-1]
            nearest = min(unvisited, key=lambda c: (c.poi.lat - last.poi.lat)**2 + (c.poi.lon - last.poi.lon)**2)
            ordered.append(nearest)
            unvisited.remove(nearest)
        return ordered
```

---

## Step 7 — `ActivityClassifierFactory`

### NEW `routeiq/activities/factory.py`

```python
from __future__ import annotations
import os
from routeiq.activities.base import ActivityClassifier
from routeiq.activities.ranker import ActivityRanker, create_ranker as _create_ranker

def create_activity_classifier(llm=None) -> ActivityClassifier:
    provider = os.getenv("ACTIVITY_PROVIDER", "osm").lower()

    if provider == "tavily":
        from routeiq.activities.tavily_classifier import TavilyActivityClassifier
        _llm = llm or _get_llm()
        return TavilyActivityClassifier(api_key=os.getenv("TAVILY_API_KEY", ""), llm=_llm)

    if provider == "perplexity":
        from routeiq.activities.perplexity_classifier import PerplexityActivityClassifier
        _llm = llm or _get_llm()
        return PerplexityActivityClassifier(api_key=os.getenv("PERPLEXITY_API_KEY", ""), llm=_llm)

    from routeiq.activities.osm_classifier import OSMActivityClassifier
    return OSMActivityClassifier()

def create_ranker(user_context: str, ratings_available: bool = False, llm=None) -> ActivityRanker:
    return _create_ranker(user_context, ratings_available, llm)

def _get_llm():
    from routeiq.llm_factory import create_llm
    return create_llm()
```

---

## Step 8 — Query Parser V3 (extract activities + user_context)

### `routeiq/insights/prompts/query_parser.py`

Add to structured output schema:
```python
class ParsedQuery(BaseModel):
    # ... existing fields ...
    activities: list[str] = []           # ["hiking", "biking", "kids"]
    user_context: str = ""               # "scenic coastal hiking" — adjective phrases only
```

New instruction added to `QUERY_PARSER_PROMPT_V3`:
```
"Extract specific physical activities the user wants to do (hiking, biking, swimming, 
 kayaking, rock climbing, kids activities, etc.) as 'activities'. 
 Return [] if none mentioned.
 Also extract any descriptive adjectives for those activities as 'user_context'
 (e.g. 'scenic coastal hiking' → user_context='scenic coastal hiking').
 If no adjectives, user_context = ''."
```

Keep `QUERY_PARSER_PROMPT_V2` intact. Add V3 alias:
```python
QUERY_PARSER_PROMPT_V3 = ...
QUERY_PARSER_PROMPT = QUERY_PARSER_PROMPT_V3
```

---

## Step 9 — Agent tool: `select_pois_for_day`

### NEW `routeiq/agent/tools/select_pois_for_day.py`

```python
from langchain_core.tools import tool
from pydantic import BaseModel
from typing import Optional

class SelectPoisInput(BaseModel):
    city: str
    requested_activities: list[str] = []
    user_context: str = ""
    total_stops: int = 5

@tool(args_schema=SelectPoisInput)
def select_pois_for_day(
    city: str,
    requested_activities: list[str],
    user_context: str,
    total_stops: int,
) -> str:
    """Select POIs for a day trip. Use when user specifies activities (hiking, biking, kids, etc.)
    or when planning a full day itinerary. Returns ranked stops split into activity-matched
    (Track 1) and scenic fills (Track 2)."""
    from routeiq.knowledge_graph.route_kg import get_kg
    from routeiq.activities.factory import create_activity_classifier, create_ranker
    from routeiq.routing.poi_selector import POISelector
    import json

    kg = get_kg()
    pois = kg.get_pois_for_city(city)
    if not pois:
        return json.dumps({"error": f"No POIs indexed for {city}"})

    classifier = create_activity_classifier()
    classified = classifier.classify_batch(city, pois, requested_activities)

    selector = POISelector()
    ranker = create_ranker(user_context, ratings_available=False)
    selected = selector.select(
        classified, requested_activities, user_context,
        ratings={}, total_stops=total_stops, ranker=ranker,
    )

    result = []
    for c in selected:
        result.append({
            "id": c.poi.id,
            "name": c.poi.name,
            "lat": c.poi.lat,
            "lon": c.poi.lon,
            "category": c.poi.category,
            "scenic_score": c.poi.scenic_score,
            "matched_activities": c.matched_activities,
            "activity_evidence": c.activity_evidence,
            "track": "activity" if c.matched_activities else "scenic",
        })

    return json.dumps({"stops": result, "total": len(result)})
```

Register in `routeiq/agent/tools/__init__.py` alongside existing tools.

The existing `find_city_pois` tool stays — agent uses `select_pois_for_day` when
`state["activities"]` is non-empty, `find_city_pois` otherwise.

---

## Step 10 — Narrate prompt V3

### `routeiq/insights/prompts/narrative.py`

Add to `NARRATIVE_PROMPT_V3` system instruction:
```
"Each stop has a 'track' field: 'activity' or 'scenic'.
 For activity stops: open with the specific activity, cite activity_evidence.
   Do NOT claim any activity not listed in matched_activities.
 For scenic stops: describe scenic quality, rating, highlights.
 Never invent claims not present in the stop data."
```

Keep V2 intact. New alias: `NARRATIVE_PROMPT = NARRATIVE_PROMPT_V3`.

---

## Step 11 — Graceful fallback

### `routeiq/agent/day_trip_agent.py` — `_plan` method, after `select_pois_for_day` returns

```python
# After tool result parsed, before draft assembly:
covered = {a for stop in selected_stops for a in stop.get("matched_activities", [])}
uncovered = set(state.get("activities", [])) - covered
if uncovered:
    state["activity_fallback_note"] = (
        f"Heads up: we couldn't find {', '.join(sorted(uncovered))} spots in {city}. "
        f"We've used the best scenic alternatives for those slots."
    )
```

Pass `activity_fallback_note` into narrate prompt when set.

---

## Step 12 — UI badge

### `app.py` — stop card render function

```python
# After stop name and rating line, before description:
if stop.matched_activities:
    cols = st.columns(len(stop.matched_activities))
    for col, act in zip(cols, stop.matched_activities):
        col.markdown(f"`{act.title()}`")
```

---

## Step 13 — Tests

| File | Tests to write |
|---|---|
| `tests/test_osm_classifier.py` | Biking tag match, hiking tag match, kids tag, no-match returns [] |
| `tests/test_activity_ranker.py` | RatingRanker sorts by rating, SemanticRanker puts coastal above inland for "scenic coastal", LLMRanker fallback on parse error |
| `tests/test_poi_selector.py` | 2 activity + 3 scenic; n_activity_slots cap at 3; empty activities = all scenic; geography ordering |
| `tests/test_tavily_classifier.py` | Mock TavilyClient + LLM; cache hit skips API call; empty results returns untagged |
| `tests/test_perplexity_classifier.py` | Mock requests.post; cache hit; parse failure returns empty dict |
| `tests/test_tavily_enrichment.py` | Mock TavilyClient; bulk hit used; per-POI fallback on miss; RatedPOI fields populated |
| `tests/test_select_pois_tool.py` | Mock KG + classifier; activities=[] falls through to find_city_pois path; JSON output shape |

Run after each step: `python3 -m pytest tests/ -v`

---

## Step 14 — LangSmith eval wiring

### NEW `eval/langsmith_dataset.py`

```python
from langsmith import Client

GOLDEN_DATASET = [
    # 15 happy path — city + activities + expected activity coverage
    {"inputs": {"city": "San Francisco, CA", "activities": ["hiking", "kids"]},
     "outputs": {"expected_activities_covered": ["hiking", "kids"],
                 "expected_track1_count": 2}},
    # ... 29 more cases ...
]

def upload():
    client = Client()
    dataset = client.create_dataset("routeiq-week4-golden", description="30 activity-based day trip cases")
    client.create_examples(
        inputs=[d["inputs"] for d in GOLDEN_DATASET],
        outputs=[d["outputs"] for d in GOLDEN_DATASET],
        dataset_id=dataset.id,
    )
```

### NEW `eval/evaluators.py`

```python
def eval_activity_recall(run, example):
    # run.outputs["stops"] — list of stop dicts with matched_activities
    # example.outputs["expected_activities_covered"]
    stops = run.outputs.get("stops", [])
    expected = set(example.outputs.get("expected_activities_covered", []))
    matched = {a for s in stops for a in s.get("matched_activities", [])}
    covered = matched & expected
    recall = len(covered) / len(expected) if expected else 1.0
    return {"key": "activity_recall", "score": recall}

def eval_activity_coverage(run, example):
    stops = run.outputs.get("stops", [])
    expected = set(example.outputs.get("expected_activities_covered", []))
    covered = {a for s in stops for a in s.get("matched_activities", [])} & expected
    coverage = len(covered) / len(expected) if expected else 1.0
    return {"key": "activity_coverage", "score": coverage}
```

### Eval run script `eval/run_week4_eval.py`

```python
# Run 4 configurations:
# 1. ACTIVITY_PROVIDER=osm,         RATING_PROVIDER=llm_synthetic  ← baseline
# 2. ACTIVITY_PROVIDER=tavily,      RATING_PROVIDER=llm_synthetic  ← classifier lift
# 3. ACTIVITY_PROVIDER=tavily,      RATING_PROVIDER=tavily_enrich  ← full Tavily
# 4. ACTIVITY_PROVIDER=perplexity,  RATING_PROVIDER=tavily_enrich  ← Perplexity classify
```

---

## Env vars needed

```bash
ACTIVITY_PROVIDER=osm          # or: tavily, perplexity
TAVILY_API_KEY=...             # from tavily.com — free tier, 1000 searches/month
PERPLEXITY_API_KEY=...         # from perplexity.ai
LANGCHAIN_PROJECT=routeiq-week4
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...          # existing key already in .env
```

---

## File creation checklist

```
NEW FILES:
  routeiq/activities/__init__.py
  routeiq/activities/base.py
  routeiq/activities/osm_classifier.py
  routeiq/activities/tavily_classifier.py
  routeiq/activities/perplexity_classifier.py
  routeiq/activities/factory.py
  routeiq/activities/ranker.py
  routeiq/ratings/tavily_enrichment.py
  routeiq/routing/poi_selector.py
  routeiq/agent/tools/select_pois_for_day.py
  eval/langsmith_dataset.py
  eval/evaluators.py
  eval/run_week4_eval.py

MODIFIED FILES:
  routeiq/ratings/base.py              add matched_activities + activity_evidence to RatedPOI
  routeiq/ratings/factory.py           register tavily_enrichment provider
  routeiq/routing/__init__.py          re-export POISelector
  routeiq/agent/tools/__init__.py      register select_pois_for_day
  routeiq/agent/day_trip_agent.py      graceful fallback + activities state field
  routeiq/insights/prompts/query_parser.py   V3 with activities + user_context
  routeiq/insights/prompts/narrative.py      V3 with two-track voice
  app.py                               activity badge in stop card
```
