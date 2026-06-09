"""Day 3 end-to-end verification: RAG enrichment + ChromaDB + vector baseline."""
from __future__ import annotations
import os

import chromadb
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from routeiq.graph.poi import POI
from routeiq.rag import WikipediaFetcher, POIIndexer, POIRetriever, VectorBaseline


# ── helpers ────────────────────────────────────────────────────────────────

def _make_sample_pois() -> list[POI]:
    return [
        POI(
            name="The Alamo",
            category="historic",
            lat=29.4260,
            lon=-98.4861,
            osm_id="alamo_1",
            wikipedia_tag="en:The Alamo",
        ),
        POI(
            name="Natural Bridge Caverns",
            category="tourism",
            lat=29.6927,
            lon=-98.3419,
            osm_id="nbc_1",
            wikipedia_tag="en:Natural Bridge Caverns",
        ),
        POI(
            name="Enchanted Rock",
            category="natural",
            lat=30.5063,
            lon=-98.8198,
            osm_id="er_1",
            wikipedia_tag="en:Enchanted Rock",
        ),
    ]


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ── verify: Wikipedia enrichment ───────────────────────────────────────────

def verify_wikipedia_fetcher(pois: list[POI]) -> list[POI]:
    _print_section("Step 1: Wikipedia enrichment")
    fetcher = WikipediaFetcher()
    for poi in pois:
        print(f"\n  Fetching: {poi.name} ...")
        fetcher.enrich(poi)
        status_desc = f"  description: {poi.description[:80]}..." if poi.description else "  description: (none)"
        status_img = f"  image_url:   {poi.image_url[:60]}..." if poi.image_url else "  image_url:   (none)"
        print(status_desc)
        print(status_img)

    enriched = sum(1 for p in pois if p.description)
    print(f"\n  Enriched {enriched}/{len(pois)} POIs with Wikipedia text")
    return pois


# ── verify: ChromaDB indexing ──────────────────────────────────────────────

def verify_chromadb(pois: list[POI]) -> tuple[POIIndexer, VectorBaseline]:
    _print_section("Step 2: ChromaDB indexing")
    client = chromadb.EphemeralClient()
    indexer = POIIndexer(client=client)
    count = indexer.index(pois)
    print(f"  Indexed {count} POIs into ChromaDB")
    print(f"  Collection count: {indexer.collection.count()}")
    return indexer, VectorBaseline(indexer)


# ── verify: retrieval by POI ID ────────────────────────────────────────────

def verify_retrieval(pois: list[POI], indexer: POIIndexer) -> None:
    _print_section("Step 3: POI retrieval by ID")
    retriever = POIRetriever(indexer)
    ids = [p.osm_id for p in pois if p.description]
    if not ids:
        print("  No enriched POIs to retrieve.")
        return
    ctx = retriever.get_context(ids)
    print(f"  Retrieved {len(ctx)} contexts")
    for osm_id, desc in list(ctx.items())[:2]:
        print(f"\n  [{osm_id}]  {desc[:100]}...")


# ── verify: vector baseline ─────────────────────────────────────────────────

def verify_vector_baseline(baseline: VectorBaseline) -> None:
    _print_section("Step 4: Vector-only baseline query")
    queries = [
        "historic missions and colonial heritage",
        "natural caves and underground geology",
        "granite rock formations",
    ]
    for q in queries:
        results = baseline.query(q, n_results=2)
        print(f"\n  Query: '{q}'")
        if results:
            for r in results:
                print(f"    → {r['name']} ({r['category']}) | score={r['similarity_score']:.3f}")
        else:
            print("    (no results)")


# ── verify: full pipeline rag node simulation ──────────────────────────────

def verify_pipeline_rag_node(pois: list[POI]) -> None:
    _print_section("Step 5: _rag_node poi_context format (pipeline simulation)")
    from routeiq.routing.scored_poi import ScoredPOI
    from routeiq.pipeline import RoutePipeline

    top_pois = [ScoredPOI(poi=p, detour_km=1.5, detour_min=2.0) for p in pois]
    poi_context = RoutePipeline._build_poi_context(top_pois)
    print(poi_context[:600])
    print("\n  [poi_context ready for narrative prompt]")


# ── main ───────────────────────────────────────────────────────────────────

def main():
    print("Day 3 Verification — RAG layer: Wikipedia + ChromaDB + vector baseline")
    print("Note: Steps 1-3 require network access to Wikipedia.")

    pois = _make_sample_pois()

    pois = verify_wikipedia_fetcher(pois)
    indexer, baseline = verify_chromadb(pois)
    verify_retrieval(pois, indexer)
    verify_vector_baseline(baseline)
    verify_pipeline_rag_node(pois)

    print("\n\nDay 3 verification complete.")
    print("Next: Day 4 — map UI, stop cards, 10-query GraphRAG vs vector baseline eval.")


if __name__ == "__main__":
    main()
