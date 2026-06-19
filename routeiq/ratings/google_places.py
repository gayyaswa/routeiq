from routeiq.graph.poi import POI
from routeiq.ratings.base import POIRatingProvider, RatedPOI


class GooglePlacesRatingProvider(POIRatingProvider):
    """Google Places rating provider — not yet implemented (Strategy pattern)."""

    @property
    def source_name(self) -> str:
        return "Google Places"

    def enrich_batch(self, city: str, pois: list[POI]) -> list[RatedPOI]:
        raise NotImplementedError("Google Places provider is not yet implemented.")
