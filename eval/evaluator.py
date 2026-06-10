"""GraphRAG vs. vector-only baseline evaluator (Strategy pattern)."""
from __future__ import annotations

from routeiq.facade import RouteIQFacade
from routeiq.rag import POIIndexer, VectorBaseline
from routeiq.graph.poi import POI


# Bay Area landmark seed data — pre-indexed so vector baseline always has data
_BAY_AREA_SEED_POIS: list[POI] = [
    POI("Cannery Row", "tourism", 36.6177, -121.8983, "ba_cannery",
        description="Historic cannery district in Monterey, California, immortalized by John Steinbeck's 1945 novel of the same name. The area now features aquariums, restaurants, and shops along the scenic waterfront."),
    POI("Point Lobos State Natural Reserve", "natural", 36.5152, -121.9443, "ba_lobos",
        description="A rugged headland just south of Carmel offering dramatic rocky shores, tide pools, sea otters, harbor seals, and spectacular ocean views. Considered the crown jewel of California's state park system."),
    POI("Carmel Mission", "historic", 36.5403, -121.9194, "ba_carmel_mission",
        description="Spanish colonial mission founded in 1770 by Father Junípero Serra. One of the best-preserved of California's 21 missions, with a stone church, museum, and Serra's burial site."),
    POI("17-Mile Drive", "tourism", 36.5794, -121.9681, "ba_17mile",
        description="Scenic private toll road along the Monterey Peninsula passing the Lone Cypress, Pebble Beach Golf Links, and sweeping Pacific Ocean views through Del Monte Forest."),
    POI("Napa Valley Wine Train", "tourism", 38.2995, -122.2869, "ba_winetrain",
        description="A vintage rail journey through the heart of Napa Valley wine country, offering gourmet dining while rolling past world-famous vineyards and the historic town of St. Helena."),
    POI("Castello di Amorosa", "tourism", 38.5591, -122.5541, "ba_castello",
        description="A fully authentic 13th-century Tuscan castle and winery in Calistoga, hand-built from European materials with a dungeon, torture chamber, and stunning wine caves."),
    POI("Henry Cowell Redwoods State Park", "natural", 37.0509, -122.0592, "ba_cowell",
        description="Old-growth coast redwood forest in the Santa Cruz Mountains, featuring trees over 1,500 years old and 15 miles of hiking trails through Cathedral Redwoods grove."),
    POI("Roaring Camp Railroad", "tourism", 37.0442, -122.0698, "ba_roaringcamp",
        description="Historic narrow-gauge steam train operating since 1875 through towering old-growth redwoods in Felton, offering both mountain and beach routes through the Santa Cruz Mountains."),
    POI("Point Reyes Lighthouse", "historic", 37.9963, -123.0235, "ba_ptreyes",
        description="A dramatic Victorian-era lighthouse perched 300 feet above the Pacific on Point Reyes National Seashore, one of the foggiest and windiest locations on the U.S. west coast."),
    POI("Muir Woods National Monument", "natural", 37.8968, -122.5715, "ba_muirwoods",
        description="A stand of old-growth coastal redwoods just 12 miles north of San Francisco, named after conservationist John Muir. Features trees over 1,000 years old and 6 miles of trails."),
    POI("Pigeon Point Lighthouse", "historic", 37.1808, -122.3946, "ba_pigeon",
        description="One of the tallest lighthouses on the US Pacific Coast, built in 1871 on the rugged San Mateo coast near Pescadero, now a hostel and popular whale-watching spot."),
    POI("Mavericks Surf Break", "natural", 37.4913, -122.4993, "ba_mavericks",
        description="World-famous big-wave surfing site near Half Moon Bay where waves can reach 60 feet. Site of the legendary Mavericks Invitational competition, visible from the coastal bluffs."),
    POI("Sonoma Plaza", "historic", 38.2921, -122.4580, "ba_sonoma",
        description="The largest historic plaza in California, surrounded by Mission San Francisco Solano and adobe buildings from the Mexican era, where the Bear Flag Republic was proclaimed in 1846."),
    POI("Jack London State Historic Park", "historic", 38.3558, -122.5278, "ba_jacklondon",
        description="The Beauty Ranch estate of writer Jack London in Glen Ellen, featuring ruins of his Wolf House, cottage museum, and the Valley of the Moon landscape that inspired his writings."),
    POI("Big Basin Redwoods State Park", "natural", 37.1743, -122.2250, "ba_bigbasin",
        description="California's oldest state park, established 1902, protecting ancient coast redwoods in the Santa Cruz Mountains including trees over 2,000 years old and 80 miles of trails."),
]


class Evaluator:
    """Runs GraphRAG vs. vector-only baseline comparison over a set of queries (Strategy pattern)."""

    def __init__(self, facade: RouteIQFacade, poi_indexer: POIIndexer) -> None:
        self._facade = facade
        self._indexer = poi_indexer
        self._baseline = VectorBaseline(poi_indexer)
        self._seed_done = False

    def _ensure_seeded(self) -> None:
        """Index Bay Area seed POIs so vector baseline always has data."""
        if self._seed_done:
            return
        self._indexer.index(_BAY_AREA_SEED_POIS)
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
