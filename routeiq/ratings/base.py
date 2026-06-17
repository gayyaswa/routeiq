from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

from routeiq.graph.poi import POI


@dataclass
class RatedPOI:
    """A POI enriched with quality signals from an external rating provider (dataclass)."""

    poi: POI
    rating: float | None = None        # normalized 0–5.0
    review_count: int | None = None
    review_snippet: str | None = None
    all_snippets: list[str] | None = None   # up to 3 review texts
    review_source: str | None = None        # "TripAdvisor" | "Foursquare" | etc.
    hours: str | None = None
    photo_urls: list[str] | None = None     # up to 5 provider photos


class POIRatingProvider(ABC):
    """Strategy ABC for enriching OSM POIs with external quality signals."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable provider name; used as the review_source badge in UI."""

    @abstractmethod
    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        """Return a RatedPOI for every poi; unmatched POIs get None quality fields."""
