"""10 Bay Area evaluation queries for GraphRAG vs. vector-only baseline comparison."""
from __future__ import annotations

# Each dict: query (str), type ("route" | "semantic"), expected_winner ("graphrag" | "vector")
# Route queries: GraphRAG wins — geographic constraints keep only on-path POIs
# Semantic queries: Vector wins (or draws) — no origin/destination context to leverage

EVAL_QUERIES: list[dict] = [
    {
        "query": "Drive from San Francisco to Muir Woods, show redwoods and coastal views",
        "type": "route",
        "expected_winner": "graphrag",
        "why": "GraphRAG constrains to SF-Marin corridor; vector retrieves any redwood/coastal POI",
    },
    {
        "query": "Road trip from San Francisco to Napa Valley, show wineries and historic towns",
        "type": "route",
        "expected_winner": "graphrag",
        "why": "GraphRAG restricts to Napa corridor; vector includes wineries anywhere in CA",
    },
    {
        "query": "Drive from San Jose to Santa Cruz, show redwoods and beaches",
        "type": "route",
        "expected_winner": "graphrag",
        "why": "GraphRAG follows HWY 17 corridor; vector returns any redwood or beach POI",
    },
    {
        "query": "Drive from San Francisco to Point Reyes, show lighthouses and coastal nature",
        "type": "route",
        "expected_winner": "graphrag",
        "why": "GraphRAG follows Marin County coast; vector finds lighthouses anywhere",
    },
    {
        "query": "Road trip from San Francisco to Half Moon Bay, show coastal cliffs and beaches",
        "type": "route",
        "expected_winner": "graphrag",
        "why": "GraphRAG follows HWY 1 south; vector returns any beach/cliff POI",
    },
    {
        "query": "Drive from San Francisco to Sausalito via the Golden Gate Bridge, show historic sites and bay views",
        "type": "route",
        "expected_winner": "graphrag",
        "why": "GraphRAG constrains to the GG Bridge / Marin Headlands corridor; vector returns any historic Bay Area site",
    },
    {
        "query": "beautiful California coastal drives",
        "type": "semantic",
        "expected_winner": "vector",
        "why": "No origin/destination — pure semantic recall; graph layer has nothing to constrain",
    },
    {
        "query": "wine country day trips from San Francisco",
        "type": "semantic",
        "expected_winner": "vector",
        "why": "Vague geography — semantic similarity to wine/winery descriptions wins",
    },
    {
        "query": "old growth redwood forests near Bay Area",
        "type": "semantic",
        "expected_winner": "vector",
        "why": "No route — pure description match for 'redwood', 'old growth', 'forest'",
    },
    {
        "query": "Gold Rush era historic towns California",
        "type": "semantic",
        "expected_winner": "vector",
        "why": "No route context — semantic match on 'Gold Rush', 'historic', 'mining town'",
    },
]
