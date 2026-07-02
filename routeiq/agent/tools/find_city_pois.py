from __future__ import annotations
import dataclasses
import json

from langchain_core.tools import tool

from routeiq.graph.knowledge_graph import get_kg


@tool
def find_city_pois(city: str) -> str:
    """Find scenic POIs within a city using the knowledge graph.

    The knowledge graph is always pre-warmed before the agent starts —
    either from the Bay Area master cache or from a pre-flight Overpass fetch.

    Args:
        city: City name, e.g. "San Francisco, CA" or "San Francisco"

    Returns:
        JSON array of up to 200 POI dicts (name, category, lat, lon, osm_id, subtype, wikipedia_tag).
    """
    pois = get_kg().get_pois_for_city(city)
    # Sort by Wikipedia presence so notable landmarks are always in the top 200.
    # en: wikipedia = most notable; other-language wiki = some notability; none = least.
    def _rank(p):
        if p.wikipedia_tag and p.wikipedia_tag.startswith("en:"):
            return 0
        if p.wikipedia_tag:
            return 1
        return 2
    pois = sorted(pois, key=_rank)
    return json.dumps([dataclasses.asdict(p) for p in pois[:200]])
