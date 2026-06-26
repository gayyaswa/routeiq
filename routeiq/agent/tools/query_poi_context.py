"""Index Wikipedia-enriched POIs into ChromaDB and retrieve KG-enriched context (Pipeline pattern)."""
from __future__ import annotations
import dataclasses
import json
from uuid import uuid4

import chromadb
from langchain_core.tools import tool

from routeiq.graph.knowledge_graph import get_kg
from routeiq.graph.poi import POI
from routeiq.rag.knowledge_rag import KnowledgeRAG
from routeiq.rag.poi_chunker import POIChunker
from routeiq.rag.poi_indexer import POIIndexer

_POI_FIELDS = {f.name for f in dataclasses.fields(POI)}


@tool
def query_poi_context(preferences: list[str], rated_pois_json: str) -> str:
    """Index rated POI Wikipedia descriptions into ChromaDB and retrieve semantically matched,
    knowledge-graph-enriched context for the itinerary narrative.

    Call this after rate_pois. Pass user preferences and the full JSON output from
    rate_pois as rated_pois_json. Returns a context block per POI with:
    - semantic match score against preferences
    - Wikipedia evidence grounded in the description
    - city and region from the knowledge graph
    - nearby POI relationships (NEAR_POI edges)

    Use this context to write specific, evidence-grounded why_visit sentences that
    reference nearby landmarks and knowledge graph relationships where relevant.

    Args:
        preferences: user preference strings, e.g. ["hiking", "historic sites"]
        rated_pois_json: JSON string — full output from the rate_pois tool
    """
    raw = json.loads(rated_pois_json)
    pois = [POI(**{k: v for k, v in d.items() if k in _POI_FIELDS}) for d in raw]

    # uuid4 collection name avoids InternalError when called repeatedly in the same process
    client = chromadb.EphemeralClient()
    indexer = POIIndexer(client=client, collection_name=f"dt_ctx_{uuid4().hex}")
    indexed = POIChunker(indexer).chunk_and_index(pois)

    if indexed == 0:
        return "No Wikipedia descriptions available — skip this tool and use description fields directly."

    context = KnowledgeRAG(indexer=indexer, knowledge_graph=get_kg()).query(
        preferences=preferences,
        route_coords=[],  # no route in day trip; Stage 2 enriches all candidates
    )
    return context if context else "No semantically relevant context found."
