"""LangGraph state machine orchestrating parse → graph → rag → narrate nodes (Pipeline pattern)."""
from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import osmnx as ox
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END

from routeiq.graph import GraphLoader, RouteGraph, POIFinder
from routeiq.graph.poi_finder import OverpassUnavailableError
from routeiq.routing import DetourScorer, POISelector
from routeiq.insights import QueryParser, NarrativeChain, FallbackChain
from routeiq.rag import WikipediaFetcher, POIIndexer, POIRetriever, POIChunker, KnowledgeRAG

_ROUTE_TOO_LONG_MIN = 360.0  # 6 hours



class PipelineState(TypedDict):
    query: str
    origin: Optional[str]
    destination: Optional[str]
    preferences: Optional[list[str]]
    origin_lat: Optional[float]
    origin_lon: Optional[float]
    dest_lat: Optional[float]
    dest_lon: Optional[float]
    route_result: Optional[Any]
    pois: Optional[list[Any]]
    top_pois: Optional[list[Any]]
    poi_context: Optional[str]
    narrative: Optional[str]
    error: Optional[str]
    fallback_reason: Optional[str]


class RoutePipeline:
    """LangGraph state machine: parse → graph → rag → narrate with conditional fallback edges (Pipeline pattern)."""

    def __init__(
        self,
        query_parser: QueryParser,
        graph_loader: GraphLoader,
        poi_finder: POIFinder,
        detour_scorer: DetourScorer,
        poi_selector: POISelector,
        narrative_chain: NarrativeChain,
        fallback_chain: FallbackChain,
        wikipedia_fetcher: WikipediaFetcher | None = None,
        poi_indexer: POIIndexer | None = None,
        poi_retriever: POIRetriever | None = None,
        poi_chunker: POIChunker | None = None,
        knowledge_rag: KnowledgeRAG | None = None,
    ) -> None:
        self._query_parser = query_parser
        self._graph_loader = graph_loader
        self._poi_finder = poi_finder
        self._detour_scorer = detour_scorer
        self._poi_selector = poi_selector
        self._narrative_chain = narrative_chain
        self._fallback_chain = fallback_chain
        self._wikipedia_fetcher = wikipedia_fetcher
        self._poi_indexer = poi_indexer
        self._poi_retriever = poi_retriever
        self._poi_chunker = poi_chunker
        self._knowledge_rag = knowledge_rag
        self._progress = lambda step, sub: None  # replaced per-run by on_progress
        self._graph = self._build_graph()

    def run(self, query: str, on_progress=None) -> dict:
        self._progress = on_progress or (lambda step, sub: None)
        initial: PipelineState = {
            "query": query,
            "origin": None,
            "destination": None,
            "preferences": None,
            "origin_lat": None,
            "origin_lon": None,
            "dest_lat": None,
            "dest_lon": None,
            "route_result": None,
            "pois": None,
            "top_pois": None,
            "poi_context": None,
            "narrative": None,
            "error": None,
            "fallback_reason": None,
        }
        return self._graph.invoke(initial)

    def _build_graph(self):
        builder = StateGraph(PipelineState)
        builder.add_node("parse", self._parse_node)
        builder.add_node("graph", self._graph_node)
        builder.add_node("rag", self._rag_node)
        builder.add_node("narrate", self._narrate_node)
        builder.set_entry_point("parse")
        builder.add_conditional_edges(
            "parse", self._route_after_parse, {"graph": "graph", "narrate": "narrate"}
        )
        builder.add_conditional_edges(
            "graph", self._route_after_graph, {"rag": "rag", "narrate": "narrate"}
        )
        builder.add_conditional_edges(
            "rag", self._route_after_rag, {"narrate": "narrate"}
        )
        builder.add_edge("narrate", END)
        return builder.compile()

    # ── nodes ──────────────────────────────────────────────────────────────

    def _parse_node(self, state: PipelineState) -> dict:
        t0 = time.perf_counter()
        self._progress("parse", "Sending query to LLM…")
        result = self._query_parser.parse(state["query"])
        print(f"[timing] parse node: {time.perf_counter()-t0:.2f}s", flush=True)
        if "_parse_error" in result:
            return {
                "error": "unparseable_query",
                "fallback_reason": (
                    f"Could not parse the query as a route intent. "
                    f"Detail: {result['_parse_error']}"
                ),
            }
        origin = result.get("origin")
        destination = result.get("destination")
        self._progress("parse", f"Parsed: {origin} → {destination}")
        return {
            "origin": origin,
            "destination": destination,
            "preferences": result.get("preferences", []),
        }

    def _graph_node(self, state: PipelineState) -> dict:
        t0 = time.perf_counter()

        self._progress("graph", f"Geocoding {state['origin']}…")
        try:
            origin_lat, origin_lon = ox.geocode(state["origin"])
            self._progress("graph", f"Geocoding {state['destination']}…")
            dest_lat, dest_lon = ox.geocode(state["destination"])
        except Exception as e:
            return {
                "error": "geocode_failed",
                "fallback_reason": (
                    f"Could not geocode '{state['origin']}' or '{state['destination']}': {e}"
                ),
            }
        print(f"[timing]   geocode: {time.perf_counter()-t0:.2f}s", flush=True)

        _PAD = 0.1
        north = max(origin_lat, dest_lat) + _PAD
        south = min(origin_lat, dest_lat) - _PAD
        east  = max(origin_lon, dest_lon) + _PAD
        west  = min(origin_lon, dest_lon) - _PAD

        self._progress("graph", "Loading OSM road network…")
        t1 = time.perf_counter()
        try:
            G = self._graph_loader.load(north=north, south=south, east=east, west=west)
        except Exception as e:
            return {
                "error": "network_error",
                "fallback_reason": f"Could not load road network from any Overpass mirror: {e}",
                "origin_lat": origin_lat,
                "origin_lon": origin_lon,
                "dest_lat": dest_lat,
                "dest_lon": dest_lon,
            }
        print(f"[timing]   graph load: {time.perf_counter()-t1:.2f}s", flush=True)

        self._progress("graph", "Computing A* shortest path…")
        t1 = time.perf_counter()
        try:
            rg = RouteGraph(G)
            route_result = rg.find_route(origin_lat, origin_lon, dest_lat, dest_lon)
        except ValueError as e:
            return {
                "error": "route_not_found",
                "fallback_reason": str(e),
                "origin_lat": origin_lat,
                "origin_lon": origin_lon,
                "dest_lat": dest_lat,
                "dest_lon": dest_lon,
            }
        print(f"[timing]   A* pathfind: {time.perf_counter()-t1:.2f}s", flush=True)

        if route_result.drive_time_min > _ROUTE_TOO_LONG_MIN:
            return {
                "error": "route_too_long",
                "fallback_reason": (
                    f"Route is {route_result.drive_time_min:.0f} min "
                    f"({route_result.length_km:.0f} km), which exceeds the 6-hour limit "
                    f"for scenic route recommendations."
                ),
                "origin_lat": origin_lat,
                "origin_lon": origin_lon,
                "dest_lat": dest_lat,
                "dest_lon": dest_lon,
                "route_result": route_result,
            }

        self._progress("graph", "Scanning route corridor for POIs…")
        t1 = time.perf_counter()
        try:
            pois = self._poi_finder.find_pois(
                route_result.route_coords,
                progress_fn=lambda msg: self._progress("graph", msg),
            )
        except OverpassUnavailableError as e:
            return {
                "error": "overpass_unavailable",
                "fallback_reason": (
                    "The OpenStreetMap POI server (Overpass API) is temporarily unavailable — "
                    "all mirrors timed out. This is a transient outage, not a problem with your query. "
                    "Please try again in a minute or two."
                ),
                "origin_lat": origin_lat,
                "origin_lon": origin_lon,
                "dest_lat": dest_lat,
                "dest_lon": dest_lon,
                "route_result": route_result,
            }
        print(f"[timing]   POI scan: {time.perf_counter()-t1:.2f}s → {len(pois)} raw POIs", flush=True)

        t1 = time.perf_counter()
        self._progress("graph", f"Scoring {len(pois)} POIs by detour cost…")
        scored = self._detour_scorer.score(pois, route_result.route_coords)
        raw_prefs = state.get("preferences") or []
        top_pois = self._poi_selector.select(scored, preferences=raw_prefs)
        print(f"[timing]   score+select: {time.perf_counter()-t1:.2f}s → {len(top_pois)} top POIs", flush=True)
        print(f"[timing] graph node total: {time.perf_counter()-t0:.2f}s", flush=True)
        self._progress("graph", f"Selected {len(top_pois)} scenic stops")

        return {
            "origin_lat": origin_lat,
            "origin_lon": origin_lon,
            "dest_lat": dest_lat,
            "dest_lon": dest_lon,
            "route_result": route_result,
            "pois": pois,
            "top_pois": top_pois,
        }

    def _rag_node(self, state: PipelineState) -> dict:
        t0 = time.perf_counter()
        if not state.get("top_pois"):
            return {
                "error": "no_pois_found",
                "fallback_reason": (
                    f"No scenic stops found near the route from "
                    f"{state['origin']} to {state['destination']}."
                ),
            }

        top_pois = state["top_pois"]

        if self._wikipedia_fetcher is not None:
            self._progress("rag", "Enriching POIs with Wikipedia…")
            t1 = time.perf_counter()
            # Each thread gets a fresh WikipediaFetcher (own Session) — safe for parallel I/O
            def _enrich(sp):
                from routeiq.rag import WikipediaFetcher as _WF
                _WF().enrich(sp.poi)

            with ThreadPoolExecutor(max_workers=min(5, len(top_pois))) as pool:
                list(pool.map(_enrich, top_pois))
            print(f"[timing]   wikipedia ({len(top_pois)} POIs parallel): {time.perf_counter()-t1:.2f}s", flush=True)

        enriched = sum(1 for sp in top_pois if sp.poi.description)
        self._progress("rag", f"Enriched {enriched}/{len(top_pois)} stops with Wikipedia descriptions")

        if self._knowledge_rag is not None:
            preferences = state.get("preferences") or []
            route_coords = state["route_result"].route_coords if state.get("route_result") else []

            if self._poi_chunker is not None:
                t1 = time.perf_counter()
                self._progress("rag", "Chunking POI descriptions…")
                pois = [sp.poi for sp in top_pois]
                self._poi_chunker.chunk_and_index(pois)
                print(f"[timing]   chunking+index: {time.perf_counter()-t1:.2f}s", flush=True)

            t1 = time.perf_counter()
            self._progress("rag", "Running 3-stage GraphRAG retrieval…")
            poi_context = self._knowledge_rag.query(
                preferences=preferences,
                route_coords=route_coords,
            )
            print(f"[timing]   knowledge_rag.query: {time.perf_counter()-t1:.2f}s", flush=True)
            if not poi_context:
                poi_context = self._build_poi_context(top_pois)
        else:
            t1 = time.perf_counter()
            self._progress("rag", "Indexing stops in ChromaDB…")
            if self._poi_indexer is not None:
                pois = [sp.poi for sp in top_pois]
                self._poi_indexer.index(pois)
            poi_context = self._build_poi_context(top_pois)
            print(f"[timing]   chroma index+context: {time.perf_counter()-t1:.2f}s", flush=True)

        print(f"[timing] rag node total: {time.perf_counter()-t0:.2f}s", flush=True)
        return {"poi_context": poi_context}

    @staticmethod
    def _build_poi_context(top_pois: list) -> str:
        lines = []
        for sp in top_pois:
            p = sp.poi
            desc = p.description or "(no description available)"
            lines.append(
                f"{p.name} | {p.category} | {sp.detour_min:.0f} min detour | {desc}"
            )
        return "\n\n".join(lines)

    def _narrate_node(self, state: PipelineState) -> dict:
        t0 = time.perf_counter()
        self._progress("narrate", "Generating route narrative…")
        if state.get("error"):
            narrative = self._fallback_chain.generate(
                reason=state.get("fallback_reason", state["error"]),
                query=state["query"],
            )
        else:
            route_result = state["route_result"]
            narrative = ""
            for chunk in self._narrative_chain.stream(
                origin=state["origin"],
                destination=state["destination"],
                distance_km=route_result.length_km,
                drive_time_min=route_result.drive_time_min,
                top_pois=state.get("top_pois") or [],
                poi_context=state.get("poi_context"),
            ):
                narrative += chunk
                self._progress("narrate_stream", chunk)
        print(f"[timing] narrate node total: {time.perf_counter()-t0:.2f}s", flush=True)
        return {"narrative": narrative}

    # ── conditional edge routers ────────────────────────────────────────────

    def _route_after_parse(self, state: PipelineState) -> str:
        if state.get("error"):
            return "narrate"
        if not state.get("origin") or not state.get("destination"):
            return "narrate"
        return "graph"

    def _route_after_graph(self, state: PipelineState) -> str:
        if state.get("error"):
            return "narrate"
        return "rag"

    def _route_after_rag(self, state: PipelineState) -> str:
        return "narrate"
