"""Orchestrates the POI knowledge coverage cascade for a city (Pipeline pattern).

Call once per city — typically right after the OSM pre-flight fetch in app.py.
Subsequent calls are near-instant: missing_or_expired() short-circuits to an
empty list once every POI is warm in the unified poi_knowledge store.

Coverage cascade per POI:
  1. Wikipedia description     → always fetched; if missing, LLM synthetic fallback
                                   description_source: "wikipedia" | "ai_generated" | ""
  2. Rating provider           → TripAdvisor / Tavily / llm_synthetic (RATING_PROVIDER env)
                                   fills rating, review_count, snippets, photos
  3. Activity classifier       → OSM tags → description-text keywords fallback
                                   activity_source: "osm" | "ai_generated" | ""
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor

from routeiq.activities.factory import create_activity_classifier
from routeiq.agent.tools.estimate_visit import _DEFAULT_MINUTES, _VISIT_MINUTES
from routeiq.graph.poi import POI
from routeiq.rag.poi_knowledge_store import POIKnowledgeStore
from routeiq.rag.wikipedia_fetcher import WikipediaFetcher
from routeiq.ratings.factory import RatingsFactory

logger = logging.getLogger(__name__)

# All 9 activity tags — classified up front so poi_knowledge.activity_tags
# reflects every activity a POI supports, not just the ones a given user requested.
_ALL_ACTIVITY_TAGS = [
    "hiking", "biking", "swimming", "kayaking", "kids",
    "picnic", "history", "food", "scenic",
]


def _wikipedia_weight(wikipedia_tag: str | None) -> float:
    """English Wikipedia article = real significance signal; other languages = stub quality."""
    if not wikipedia_tag:
        return 0.0
    return 0.1 if wikipedia_tag.startswith("en:") else 0.01


def _composite_score(rating: float | None, review_count: int | None, wikipedia_tag: str | None) -> float:
    """Blend rating (40%), review volume (30%), and Wikipedia presence (30%) into one rank score."""
    r = (rating / 5.0) if rating is not None else 0.5
    v = math.log1p(review_count or 0) / math.log1p(10_000)
    w = _wikipedia_weight(wikipedia_tag)
    return round(0.4 * r + 0.3 * v + 0.3 * w, 4)


def _visit_minutes(poi: POI) -> int:
    """Look up the typical visit duration for this POI's subtype, with a default fallback."""
    return _VISIT_MINUTES.get((poi.subtype or "").lower(), _DEFAULT_MINUTES)


def _wiki_enrich(poi: POI) -> None:
    """Fetch and attach a Wikipedia description to the POI in place, if it doesn't have one yet."""
    if not poi.description:
        WikipediaFetcher().enrich(poi)


def _synthetic_enrich(poi: POI, city: str) -> None:
    """Fill poi.description via LLM when Wikipedia returned nothing."""
    from routeiq.rag.synthetic_describer import describe as _synth_desc
    desc = _synth_desc(poi, city)
    if desc:
        poi.description = desc


class CityPrefetcher:
    """Runs the Wikipedia + ratings + activity-tagging cascade for a city (Pipeline pattern)."""

    def __init__(self, store: POIKnowledgeStore | None = None) -> None:
        self._store = store or POIKnowledgeStore()

    def prefetch(self, city: str, pois: list[POI]) -> int:
        """Enrich and index any POIs missing from the unified knowledge store.

        Skips POIs already warm (within the 50-day TTL) so repeat calls for the
        same city are cheap. Returns the number of POIs newly indexed (0 = all warm).
        """
        if not pois:
            return 0

        by_name = {p.name: p for p in pois}
        to_enrich = self._store.missing_or_expired(city, list(by_name.keys()))
        if not to_enrich:
            logger.info("CityPrefetcher: all %d POIs warm for %r", len(pois), city)
            return 0

        target_pois = [by_name[n] for n in to_enrich]
        logger.info("CityPrefetcher: enriching %d/%d POIs for %r", len(target_pois), len(pois), city)

        # ── Wikipedia descriptions ────────────────────────────────────────────
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_wiki_enrich, target_pois))

        # Synthetic description fallback for POIs Wikipedia didn't cover.
        _no_desc = [p for p in target_pois if not p.description]
        if _no_desc:
            logger.info("CityPrefetcher: synthetic descriptions for %d/%d POIs", len(_no_desc), len(target_pois))
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda p: _synthetic_enrich(p, city), _no_desc))
        _synth_names = {p.name for p in _no_desc if p.description}

        description_sources = {
            poi.name: (
                "ai_generated" if poi.name in _synth_names
                else "wikipedia" if poi.description
                else ""
            )
            for poi in target_pois
        }

        # ── Rating provider ───────────────────────────────────────────────────
        # Primary provider (Tavily or configured RATING_PROVIDER). If rate-limited
        # or the provider returned no data for a POI, fall back to LLM synthetic.
        rated = RatingsFactory.create().enrich_batch(city, target_pois)
        rated = self._synthetic_fallback(city, rated)
        rated_by_name = {rp.poi.name: rp for rp in rated}

        # ── Activity classifier ───────────────────────────────────────────────
        # Tags each POI against all 9 activities: OSM tags → name keywords → description
        # keywords (same _CATEGORY_KEYWORDS dict, no duplication).
        classifier = create_activity_classifier()
        classified = classifier.classify_batch(city, target_pois, _ALL_ACTIVITY_TAGS)
        classified_by_name = {c.poi.name: c for c in classified}

        # Derive activity_source from activity_evidence set by the classifier.
        activity_sources = {
            c.poi.name: (
                "osm" if (c.activity_evidence or "").startswith("osm")
                else "ai_generated" if c.matched_activities   # name or description match
                else ""
            )
            for c in classified
        }

        entries = self._build_entries(
            target_pois, rated_by_name, classified_by_name,
            description_sources, activity_sources,
        )
        self._store.upsert_batch(city, entries)
        logger.info("CityPrefetcher: upserted %d entries for %r", len(entries), city)
        return len(entries)

    def _synthetic_fallback(self, city: str, rated: list) -> list:
        """Replace un-enriched RatedPOIs with LLM-synthetic ratings."""
        unenriched = [rp.poi for rp in rated if rp.rating is None and not rp.review_snippet]
        if not unenriched:
            return rated
        logger.info("CityPrefetcher: synthetic fallback for %d un-enriched POIs", len(unenriched))
        from routeiq.ratings.llm_synthetic import LLMSyntheticRatingProvider
        synthetic = LLMSyntheticRatingProvider().enrich_batch(city, unenriched)
        synthetic_by_name = {r.poi.name: r for r in synthetic}
        return [
            synthetic_by_name.get(rp.poi.name, rp)
            if (rp.rating is None and not rp.review_snippet)
            else rp
            for rp in rated
        ]

    def _build_entries(
        self,
        pois: list[POI],
        rated_by_name: dict,
        classified_by_name: dict,
        description_sources: dict | None = None,
        activity_sources: dict | None = None,
    ) -> list[dict]:
        """Assemble one poi_knowledge entry dict per POI from the three cascade outputs."""
        description_sources = description_sources or {}
        activity_sources = activity_sources or {}
        entries = []
        for poi in pois:
            rp = rated_by_name.get(poi.name)
            cp = classified_by_name.get(poi.name)
            rating = rp.rating if rp else None
            review_count = rp.review_count if rp else None
            entry: dict = {
                "poi_name":              poi.name,
                "category":              poi.category or "",
                "subtype":               poi.subtype or "",
                "lat":                   poi.lat,
                "lon":                   poi.lon,
                "osm_id":                poi.osm_id or "",
                "wikipedia_tag":         poi.wikipedia_tag or "",
                "wikipedia_description": poi.description or "",
                "image_url":             poi.image_url or "",
                "rating":                rating,
                "review_count":          review_count,
                "all_snippets":          (rp.all_snippets if rp else None) or [],
                "review_snippet":        (rp.review_snippet if rp else None) or "",
                "review_source":         (rp.review_source if rp else None) or "none",
                "photo_urls":            (rp.photo_urls if rp else None) or [],
                "hours":                 (rp.hours if rp else None) or "",
                "has_wikipedia":         "true" if poi.description else "false",
                "has_provider":          "true" if rating is not None else "false",
                "composite_score":       _composite_score(rating, review_count, poi.wikipedia_tag),
                "visit_duration_min":    _visit_minutes(poi),
                "activity_tags":         (cp.matched_activities if cp else None) or [],
                "activity_evidence":     (cp.activity_evidence if cp else None) or "",
                "description_source":    description_sources.get(poi.name, ""),
                "activity_source":       activity_sources.get(poi.name, ""),
            }
            entries.append(entry)
        return entries
