from __future__ import annotations
import dataclasses
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from routeiq.graph.poi import POI
from routeiq.rag.poi_knowledge_store import POIKnowledgeStore
from routeiq.ratings.factory import RatingsFactory
from routeiq.rag.wikipedia_fetcher import WikipediaFetcher
from routeiq.agent.tools.estimate_visit import _VISIT_MINUTES, _DEFAULT_MINUTES

_TOP_N = 30
_ACTIVITY_PASSTHROUGH_FIELDS = ("matched_activities", "activity_evidence", "track")
_POI_FIELDS: set[str] | None = None  # lazily populated

# poi_knowledge metadata fields that map straight onto a rate_pois output entry.
_KNOWLEDGE_TO_ENTRY_FIELDS = (
    "rating", "review_count", "review_snippet", "all_snippets",
    "review_source", "photo_urls", "hours", "visit_duration_min", "composite_score",
)


def _poi_fields() -> set[str]:
    """Lazily compute and cache the set of POI dataclass field names."""
    global _POI_FIELDS
    if _POI_FIELDS is None:
        _POI_FIELDS = {f.name for f in dataclasses.fields(POI)}
    return _POI_FIELDS


def _wikipedia_weight(wikipedia_tag: str | None) -> float:
    """English Wikipedia = real significance signal; Cebuano/other = auto-generated stubs."""
    if not wikipedia_tag:
        return 0.0
    return 0.1 if wikipedia_tag.startswith("en:") else 0.01


def _composite_score(rating: float | None, review_count: int | None, wikipedia_tag: str | None) -> float:
    """Blend rating (40%), review volume (30%), and Wikipedia presence (30%) into one rank score."""
    r = (rating / 5.0) if rating is not None else 0.5
    v = math.log1p(review_count or 0) / math.log1p(10_000)
    w = _wikipedia_weight(wikipedia_tag)
    return 0.4 * r + 0.3 * v + 0.3 * w


def _keep(entry: dict) -> bool:
    """Drop only when BOTH rating is poor AND review count is low.

    With llm_synthetic the LLM is constrained to 3.8–4.9, so this filter
    never fires for synthetic data. It matters with real providers (TripAdvisor,
    Foursquare, Tavily) where genuinely bad venues can surface from OSM.
    """
    rating = entry.get("rating")
    if rating is None:
        return True
    return not (rating < 3.8 and (entry.get("review_count") or 0) < 20)


def _wiki_enrich(poi: POI) -> None:
    """Fetch and attach a Wikipedia description to the POI in place, if it doesn't have one yet."""
    if not poi.description:
        WikipediaFetcher().enrich(poi)


def _entry_from_knowledge(poi: POI, knowledge: dict, extra: dict) -> dict:
    """Build a rate_pois output entry from a poi_knowledge metadata hit + POI geometry."""
    entry = dataclasses.asdict(poi)
    for field in _KNOWLEDGE_TO_ENTRY_FIELDS:
        entry[field] = knowledge.get(field)
    entry["all_snippets"] = knowledge.get("all_snippets") or []
    entry["photo_urls"] = knowledge.get("photo_urls") or []
    entry.update(extra)
    return entry


def _build_entry(rp, extra: dict) -> dict:
    """Assemble a full rated-POI output dict from a RatedPOI + activity passthrough fields."""
    entry = dataclasses.asdict(rp.poi)
    entry["rating"] = rp.rating
    entry["review_count"] = rp.review_count
    entry["review_snippet"] = rp.review_snippet
    entry["all_snippets"] = rp.all_snippets or []
    entry["review_source"] = rp.review_source
    entry["photo_urls"] = rp.photo_urls or []
    entry["hours"] = rp.hours
    entry["visit_duration_min"] = _VISIT_MINUTES.get(
        (rp.poi.subtype or "").lower(), _DEFAULT_MINUTES
    )
    entry["composite_score"] = round(
        _composite_score(rp.rating, rp.review_count, rp.poi.wikipedia_tag), 4
    )
    entry.update(extra)
    return entry


@tool
def rate_pois(city: str, poi_list_json: str, config: RunnableConfig) -> str:
    """Enrich a list of POIs with ratings and return the top 30 ranked by quality.

    Args:
        city: City name used for the ratings lookup, e.g. "San Francisco, CA"
        poi_list_json: JSON string — array of POI dicts as returned by find_city_pois

    Returns:
        JSON array of up to 30 dicts, each with all POI fields plus
        rating (0–5), review_count, review_snippet, hours, and composite_score.
        Sorted best-first.
    """
    from routeiq.timing import log as _tlog

    _raw = json.loads(poi_list_json)
    # Unwrap the {_note, pois} envelope returned by select_pois_for_day when no
    # activity-matched POIs were found — rate_pois only needs the pois list.
    raw: list[dict] = _raw.get("pois", []) if isinstance(_raw, dict) else _raw
    fields = _poi_fields()
    pois = [POI(**{k: v for k, v in d.items() if k in fields}) for d in raw]
    extra_by_name: dict[str, dict] = {
        d["name"]: {k: v for k, v in d.items() if k in _ACTIVITY_PASSTHROUGH_FIELDS}
        for d in raw
    }

    # ── Layer 1: in-session LangGraph state cache (zero latency) ─────────────
    session_cache: dict = (config.get("configurable") or {}).get("poi_cache", {})

    hits: list[dict] = []
    misses: list[POI] = []

    for poi in pois:
        key = f"{city}||{poi.name}"
        if key in session_cache:
            entry = dict(session_cache[key])
            entry.update(extra_by_name.get(poi.name, {}))
            hits.append(entry)
        else:
            misses.append(poi)

    if misses:
        # ── Layer 2: unified poi_knowledge store (prefetched at city load) ────
        # Plan A — provider calls happen once at prefetch time, not inside the
        # ReAct loop, so a warm city resolves here in one ChromaDB round-trip.
        _t_know = time.perf_counter()
        store = POIKnowledgeStore()
        miss_names = [poi.name for poi in misses]
        knowledge_hits = store.get_metadata(city, miss_names)
        _tlog(f"rate_pois poi_knowledge={time.perf_counter()-_t_know:.2f}s hits={len(knowledge_hits)}/{len(misses)}")
        still_missing: list[POI] = []

        for poi in misses:
            knowledge = knowledge_hits.get(poi.name)
            if knowledge is not None:
                entry = _entry_from_knowledge(poi, knowledge, extra_by_name.get(poi.name, {}))
                hits.append(entry)
                session_cache[f"{city}||{poi.name}"] = entry
            else:
                still_missing.append(poi)

        if still_missing:
            # ── Cold-path fallback: city was never prefetched — fetch directly.
            # Costs API calls inline (the behavior Plan A's prefetch step is meant
            # to eliminate), but keeps rate_pois correct even without a prior prefetch.
            _t_wiki = time.perf_counter()
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(_wiki_enrich, still_missing))
            _tlog(f"rate_pois wikipedia={time.perf_counter()-_t_wiki:.2f}s pois={len(still_missing)}")

            _t_rate = time.perf_counter()
            rated = RatingsFactory.create().enrich_batch(city, still_missing)
            _tlog(f"rate_pois provider={time.perf_counter()-_t_rate:.2f}s")

            knowledge_entries: list[dict] = []
            for rp in rated:
                extra = extra_by_name.get(rp.poi.name, {})
                entry = _build_entry(rp, extra)
                session_cache[f"{city}||{rp.poi.name}"] = entry
                hits.append(entry)
                knowledge_entries.append({
                    **entry,
                    "poi_name": rp.poi.name,
                    "wikipedia_description": rp.poi.description or "",
                })

            store.upsert_batch(city, knowledge_entries)

    scored = sorted(
        [e for e in hits if _keep(e)],
        key=lambda e: e.get("composite_score") or 0.0,
        reverse=True,
    )
    return json.dumps(scored[:_TOP_N])
