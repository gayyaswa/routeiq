from __future__ import annotations
import dataclasses
import json

from langchain_core.tools import tool

from routeiq.graph.knowledge_graph import RouteKnowledgeGraph


@tool
def find_city_pois(city: str, categories: list[str]) -> str:
    """Find scenic POIs within a city using the knowledge graph.

    The knowledge graph is always pre-warmed before the agent starts —
    either from the Bay Area master cache or from a pre-flight Overpass fetch.

    Args:
        city: City name, e.g. "San Francisco, CA" or "San Francisco"
        categories: OSM categories to include — any subset of ["tourism", "historic", "natural"].
                    Pass an empty list to include all categories.

    Returns:
        JSON array of up to 100 POI dicts (name, category, lat, lon, osm_id, subtype, wikipedia_tag).
    """
    pois = RouteKnowledgeGraph().get_pois_for_city(city)

    if categories:
        pois = [p for p in pois if p.category in categories]

    return json.dumps([dataclasses.asdict(p) for p in pois[:100]])
