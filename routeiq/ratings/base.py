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
    hours: str | None = None


class POIRatingProvider(ABC):
    """Strategy ABC for enriching OSM POIs with external quality signals."""

    @abstractmethod
    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        """Return a RatedPOI for every poi; unmatched POIs get None quality fields."""
