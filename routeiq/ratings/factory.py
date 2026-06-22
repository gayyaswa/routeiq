from __future__ import annotations
import os

from routeiq.graph.poi import POI
from routeiq.ratings.base import POIRatingProvider, RatedPOI


class _NullRatingProvider(POIRatingProvider):
    """Pass-through when no rating API key is configured (Null Object pattern)."""

    @property
    def source_name(self) -> str:
        return "Unknown"

    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        return [RatedPOI(poi=p) for p in pois]


class RatingsFactory:
    """Creates the active POIRatingProvider from environment configuration (Factory pattern)."""

    @staticmethod
    def create() -> POIRatingProvider:
        provider = os.getenv("RATING_PROVIDER", "foursquare").lower()

        if provider == "foursquare":
            api_key = os.getenv("FOURSQUARE_API_KEY", "")
            if not api_key:
                return _NullRatingProvider()
            from routeiq.ratings.foursquare import FoursquareRatingProvider
            return FoursquareRatingProvider(api_key=api_key)

        if provider == "tripadvisor":
            api_key = os.getenv("TRIPADVISOR_API_KEY", "")
            if not api_key:
                return _NullRatingProvider()
            from routeiq.ratings.tripadvisor import TripAdvisorRatingProvider
            return TripAdvisorRatingProvider(api_key=api_key)

        if provider == "google_places":
            from routeiq.ratings.google_places import GooglePlacesRatingProvider
            return GooglePlacesRatingProvider()

        if provider == "llm_synthetic":
            from routeiq.ratings.llm_synthetic import LLMSyntheticRatingProvider
            return LLMSyntheticRatingProvider()

        if provider == "tavily_enrichment":
            api_key = os.getenv("TAVILY_API_KEY", "")
            if not api_key:
                return _NullRatingProvider()
            from routeiq.ratings.tavily_enrichment import TavilyEnrichmentProvider
            from routeiq.llm_factory import create_llm
            return TavilyEnrichmentProvider(api_key=api_key, llm=create_llm())

        return _NullRatingProvider()
