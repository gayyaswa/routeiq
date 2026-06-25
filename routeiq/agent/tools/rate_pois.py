from __future__ import annotations
import dataclasses
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor

from langchain_core.tools import tool

from routeiq.graph.poi import POI
from routeiq.ratings.factory import RatingsFactory
from routeiq.rag.wikipedia_fetcher import WikipediaFetcher
from routeiq.agent.tools.estimate_visit import _VISIT_MINUTES, _DEFAULT_MINUTES

_TOP_N = 30
# Extra fields injected by select_pois_for_day that are not POI dataclass fields.
# rate_pois must carry them forward so the LLM can cite matched activities.
_ACTIVITY_PASSTHROUGH_FIELDS = ("matched_activities", "activity_evidence", "track")


def _wikipedia_weight(wikipedia_tag: str | None) -> float:
    """English Wikipedia = real significance signal; Cebuano/other = auto-generated stubs."""
    if not wikipedia_tag:
        return 0.0
    return 0.1 if wikipedia_tag.startswith("en:") else 0.01


def _composite_score(rating: float | None, review_count: int | None, wikipedia_tag: str | None) -> float:
    r = (rating / 5.0) if rating is not None else 0.5        # unknown → neutral
    v = math.log1p(review_count or 0) / math.log1p(10_000)
    w = _wikipedia_weight(wikipedia_tag)
    return 0.4 * r + 0.3 * v + 0.3 * w


@tool
def rate_pois(city: str, poi_list_json: str) -> str:
    """Enrich a list of POIs with Foursquare ratings and return the top 30 ranked by quality.

    Args:
        city: City name used for the ratings lookup, e.g. "San Francisco, CA"
        poi_list_json: JSON string — array of POI dicts as returned by find_city_pois

    Returns:
        JSON array of up to 30 dicts, each with all POI fields plus
        rating (0–5), review_count, review_snippet, hours, and composite_score.
        Sorted best-first.
    """
    raw = json.loads(poi_list_json)
    _poi_fields = {f.name for f in dataclasses.fields(POI)}
    pois = [POI(**{k: v for k, v in d.items() if k in _poi_fields}) for d in raw]

    # Preserve activity metadata (from select_pois_for_day) keyed by POI name
    # so it survives the POI reconstruction and appears in the output.
    _extra_by_name: dict[str, dict] = {
        d["name"]: {k: v for k, v in d.items() if k in _ACTIVITY_PASSTHROUGH_FIELDS}
        for d in raw
    }

    # Fetch Wikipedia descriptions in parallel for any POI that lacks one.
    # This avoids relying on the LLM to make N separate enrich_poi_details calls.
    def _wiki_enrich(poi: POI) -> None:
        if not poi.description:
            WikipediaFetcher().enrich(poi)

    from routeiq.timing import log as _tlog
    _t_wiki = time.perf_counter()
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_wiki_enrich, pois))
    _tlog(f"rate_pois wikipedia={time.perf_counter()-_t_wiki:.2f}s pois={len(pois)}")

    _t_rate = time.perf_counter()
    rated = RatingsFactory.create().enrich_batch(city, pois)
    _tlog(f"rate_pois llm_synthetic={time.perf_counter()-_t_rate:.2f}s")

    # Filter: drop only when BOTH rating is poor AND review count is low
    def _keep(rp) -> bool:
        if rp.rating is None:
            return True
        low_rating = rp.rating < 3.8
        low_reviews = (rp.review_count or 0) < 20
        return not (low_rating and low_reviews)

    kept = [rp for rp in rated if _keep(rp)]

    scored = sorted(
        kept,
        key=lambda rp: _composite_score(rp.rating, rp.review_count, rp.poi.wikipedia_tag),
        reverse=True,
    )

    results = []
    for rp in scored[:_TOP_N]:
        entry = dataclasses.asdict(rp.poi)
        entry["rating"] = rp.rating
        entry["review_count"] = rp.review_count
        entry["review_snippet"] = rp.review_snippet
        entry["all_snippets"] = rp.all_snippets or []
        entry["review_source"] = rp.review_source
        entry["photo_urls"] = rp.photo_urls or []
        entry["hours"] = rp.hours
        entry["visit_duration_min"] = _VISIT_MINUTES.get((rp.poi.subtype or "").lower(), _DEFAULT_MINUTES)
        entry["composite_score"] = round(
            _composite_score(rp.rating, rp.review_count, rp.poi.wikipedia_tag), 4
        )
        # Carry forward activity metadata from select_pois_for_day
        entry.update(_extra_by_name.get(rp.poi.name, {}))
        results.append(entry)

    return json.dumps(results)
