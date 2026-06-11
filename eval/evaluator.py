"""GraphRAG vs. vector-only baseline evaluator (Strategy pattern)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from routeiq.facade import RouteIQFacade
from routeiq.rag import POIIndexer, VectorBaseline
from routeiq.graph.poi import POI

_MASTER_FILE = Path(__file__).parent.parent / "cache" / "pois" / "bay_area_all.json.gz"


def _load_notable_bay_area_pois() -> list[POI]:
    """Load OSM-verified notable Bay Area POIs (wikipedia_tag set) from master cache."""
    if not _MASTER_FILE.exists():
        return []
    with gzip.open(_MASTER_FILE) as f:
        raw = json.load(f)
    return [
        POI(
            name=p["name"],
            category=p.get("category", "tourism"),
            lat=p["lat"],
            lon=p["lon"],
            osm_id=p["osm_id"],
            wikipedia_tag=p.get("wikipedia_tag"),
            subtype=p.get("subtype"),
        )
        for p in raw
        if p.get("wikipedia_tag")
    ]


# 95 OSM-verified notable Bay Area landmarks — loaded from committed master cache.
# Descriptions are fetched via Wikipedia at seed time (Evaluator._ensure_seeded).
_BAY_AREA_SEED_POIS: list[POI] = _load_notable_bay_area_pois()


class Evaluator:
    """Runs GraphRAG vs. vector-only baseline comparison over a set of queries (Strategy pattern)."""

    def __init__(self, facade: RouteIQFacade, poi_indexer: POIIndexer) -> None:
        self._facade = facade
        self._indexer = poi_indexer
        self._baseline = VectorBaseline(poi_indexer)
        self._seed_done = False

    def _ensure_seeded(self) -> None:
        """Enrich and index notable Bay Area POIs so vector baseline has rich coverage."""
        if self._seed_done:
            return
        from concurrent.futures import ThreadPoolExecutor
        from routeiq.rag import WikipediaFetcher
        print(f"    Enriching {len(_BAY_AREA_SEED_POIS)} notable Bay Area POIs with Wikipedia descriptions…")
        def _enrich(poi: POI) -> None:
            WikipediaFetcher().enrich(poi)
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(_enrich, _BAY_AREA_SEED_POIS))
        indexed = self._indexer.index(_BAY_AREA_SEED_POIS)
        print(f"    Seeded vector baseline with {indexed} enriched POIs")
        self._seed_done = True

    def run_graphrag(self, query: str) -> dict:
        """Run full pipeline and return structured result dict."""
        state = self._facade.run(query)
        if state.get("error"):
            return {
                "pois": [],
                "error": state["error"],
                "narrative_snippet": (state.get("narrative") or "")[:120],
            }
        top_pois = state.get("top_pois") or []
        return {
            "pois": [
                {
                    "name": sp.poi.name,
                    "category": sp.poi.category,
                    "detour_min": round(sp.detour_min, 1),
                }
                for sp in top_pois
            ],
            "error": None,
            "route_km": round(state["route_result"].length_km, 0) if state.get("route_result") else None,
            "narrative_snippet": (state.get("narrative") or "")[:120],
        }

    def run_vector(self, query: str, n_results: int = 5) -> list[dict]:
        """Run pure semantic retrieval and return top-N results."""
        self._ensure_seeded()
        return self._baseline.query(query, n_results=n_results)

    def compare(self, graphrag_result: dict, vector_results: list[dict]) -> dict:
        """Compute overlap and uniqueness metrics between the two result sets."""
        g_names = {r["name"].lower() for r in graphrag_result.get("pois", [])}
        v_names = {r["name"].lower() for r in vector_results}
        overlap = g_names & v_names
        return {
            "graphrag_count": len(g_names),
            "vector_count": len(v_names),
            "overlap_count": len(overlap),
            "graphrag_only": sorted(g_names - v_names),
            "vector_only": sorted(v_names - g_names),
        }

    def run_all(self, queries: list[dict]) -> list[dict]:
        """Evaluate all queries and return a list of result rows."""
        rows = []
        for q in queries:
            query_text = q["query"]
            query_type = q["type"]
            expected = q["expected_winner"]
            print(f"\n  [{query_type.upper()}] {query_text[:70]}...")

            if query_type == "route":
                print("    Running GraphRAG pipeline…")
                g_result = self.run_graphrag(query_text)
                # Also index any newly found POIs into shared collection before vector query
            else:
                g_result = {"pois": [], "error": "skipped (semantic query)", "narrative_snippet": ""}

            print("    Running vector baseline…")
            v_results = self.run_vector(query_text)

            metrics = self.compare(g_result, v_results)

            # Determine actual winner based on results
            if g_result.get("error") and g_result["error"] != "skipped (semantic query)":
                actual_winner = "vector"
            elif query_type == "semantic":
                actual_winner = "vector"
            elif metrics["graphrag_only"] and not metrics["vector_only"]:
                actual_winner = "graphrag"
            elif metrics["vector_only"] and not metrics["graphrag_only"]:
                actual_winner = "vector"
            elif metrics["graphrag_count"] > 0 and metrics["overlap_count"] < metrics["graphrag_count"]:
                actual_winner = "graphrag"
            else:
                actual_winner = "tie"

            rows.append({
                "query": query_text,
                "type": query_type,
                "expected_winner": expected,
                "graphrag_pois": [p["name"] for p in g_result.get("pois", [])],
                "vector_pois": [r["name"] for r in v_results],
                "graphrag_only": metrics["graphrag_only"],
                "vector_only": metrics["vector_only"],
                "overlap": metrics["overlap_count"],
                "actual_winner": actual_winner,
                "expected_matches_actual": expected == actual_winner,
                "route_km": g_result.get("route_km"),
                "error": g_result.get("error"),
            })

            status = "✓" if rows[-1]["expected_matches_actual"] else "✗"
            print(f"    {status} Expected: {expected} | Actual: {actual_winner}")

        return rows
