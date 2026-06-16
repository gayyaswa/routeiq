from __future__ import annotations
import dataclasses
import json
import math

from langchain_core.tools import tool

from routeiq.graph.poi import POI
from routeiq.ratings.factory import RatingsFactory

_TOP_N = 30


def _composite_score(rating: float | None, review_count: int | None, has_wikipedia: bool) -> float:
    r = (rating / 5.0) if rating is not None else 0.5        # unknown → neutral
    v = math.log1p(review_count or 0) / math.log1p(10_000)
    w = 0.1 if has_wikipedia else 0.0
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
    pois = [POI(**d) for d in raw]

    rated = RatingsFactory.create().enrich_batch(city, pois)

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
        key=lambda rp: _composite_score(rp.rating, rp.review_count, bool(rp.poi.wikipedia_tag)),
        reverse=True,
    )

    results = []
    for rp in scored[:_TOP_N]:
        entry = dataclasses.asdict(rp.poi)
        entry["rating"] = rp.rating
        entry["review_count"] = rp.review_count
        entry["review_snippet"] = rp.review_snippet
        entry["hours"] = rp.hours
        entry["composite_score"] = round(
            _composite_score(rp.rating, rp.review_count, bool(rp.poi.wikipedia_tag)), 4
        )
        results.append(entry)

    return json.dumps(results)
