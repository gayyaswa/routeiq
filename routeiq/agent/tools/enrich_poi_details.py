from __future__ import annotations
import json

from langchain_core.tools import tool

from routeiq.graph.poi import POI
from routeiq.rag.wikipedia_fetcher import WikipediaFetcher


@tool
def enrich_poi_details(poi_name: str, city: str) -> str:
    """Fetch a Wikipedia description and thumbnail image URL for a named POI.

    Args:
        poi_name: Display name of the POI, e.g. "Alcatraz Island"
        city: City context to help disambiguate Wikipedia search, e.g. "San Francisco, CA"

    Returns:
        JSON with description (str | null) and image_url (str | null).
    """
    poi = POI(
        name=poi_name,
        category="tourism",
        lat=0.0,
        lon=0.0,
        osm_id="agent_lookup",
    )
    WikipediaFetcher().enrich(poi)
    return json.dumps({"description": poi.description, "image_url": poi.image_url})
