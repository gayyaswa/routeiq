"""Query the unified POI knowledge store for narrative-grounding context (Pipeline pattern)."""
from __future__ import annotations
import json

from langchain_core.tools import tool

from routeiq.graph.knowledge_graph import get_kg
from routeiq.rag.poi_knowledge_store import POIKnowledgeStore


def _format_context(hits: list[dict]) -> str:
    """Format poi_knowledge query hits into one context line per POI for the narrative LLM."""
    kg = get_kg()
    lines = []
    for hit in hits:
        osm_id = hit.get("osm_id") or ""
        graph_data = kg.enrich_poi(osm_id) if osm_id else {}
        nearby = ", ".join(graph_data.get("nearby_pois", [])[:3]) or "none"
        evidence = hit.get("wikipedia_description") or hit.get("review_snippet") or ""
        lines.append(
            f"{hit.get('poi_name', '?')} | {hit.get('category', '?')} | "
            f"{graph_data.get('city', '?')} | {graph_data.get('region', '?')} | "
            f"nearby: {nearby} | {evidence}"
        )
    return "\n\n".join(lines)


@tool
def query_poi_context(preferences: list[str], rated_pois_json: str) -> str:
    """Query the unified POI knowledge store for semantically matched, knowledge-graph-enriched
    context for the itinerary narrative.

    Call this after rate_pois. Wikipedia + TripAdvisor + Tavily text for every POI was
    already embedded into the knowledge store at city load — this tool does a single
    semantic query against that pre-built index, scoped to the rated_pois shortlist.
    No re-indexing happens here.

    Args:
        preferences: user preference strings, e.g. ["hiking", "historic sites"]
        rated_pois_json: JSON string — full output from the rate_pois tool

    Returns:
        A context block per matched POI: name, category, city/region, nearby POIs, and
        grounding evidence text. Use this to write specific, evidence-grounded why_visit sentences.
    """
    raw = json.loads(rated_pois_json)
    poi_names = [d.get("name") for d in raw if d.get("name")]
    if not poi_names:
        return "No POIs available — use description fields directly."

    store = POIKnowledgeStore()
    query_text = " ".join(preferences) if preferences else "scenic landmark"
    hits = store.query_within(poi_names, query_text, n=10)

    if not hits:
        return "No semantically relevant context found."

    return _format_context(hits)
