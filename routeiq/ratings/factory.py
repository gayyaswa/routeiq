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

        return _NullRatingProvider()
