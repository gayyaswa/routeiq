"""LangGraph state machine orchestrating parse → graph → rag → narrate nodes (Pipeline pattern)."""
from __future__ import annotations
from typing import Any, Optional

import osmnx as ox
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END

from routeiq.graph import GraphLoader, RouteGraph, POIFinder
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
        self._graph = self._build_graph()

    def run(self, query: str) -> dict:
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
        result = self._query_parser.parse(state["query"])
        if "_parse_error" in result:
            return {
                "error": "unparseable_query",
                "fallback_reason": (
                    f"Could not parse the query as a route intent. "
                    f"Detail: {result['_parse_error']}"
                ),
            }
        return {
            "origin": result.get("origin"),
            "destination": result.get("destination"),
            "preferences": result.get("preferences", []),
        }

    def _graph_node(self, state: PipelineState) -> dict:
        try:
            origin_lat, origin_lon = ox.geocode(state["origin"])
            dest_lat, dest_lon = ox.geocode(state["destination"])
        except Exception as e:
            return {
                "error": "geocode_failed",
                "fallback_reason": (
                    f"Could not geocode '{state['origin']}' or '{state['destination']}': {e}"
                ),
            }

        _PAD = 0.1
        north = max(origin_lat, dest_lat) + _PAD
        south = min(origin_lat, dest_lat) - _PAD
        east  = max(origin_lon, dest_lon) + _PAD
        west  = min(origin_lon, dest_lon) - _PAD

        G = self._graph_loader.load(north=north, south=south, east=east, west=west)

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

        pois = self._poi_finder.find_pois(route_result.route_coords)
        scored = self._detour_scorer.score(pois, route_result.route_coords)
        top_pois = self._poi_selector.select(scored, preferences=state.get("preferences") or [])

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
        if not state.get("top_pois"):
            return {
                "error": "no_pois_found",
                "fallback_reason": (
                    f"No scenic stops found near the route from "
                    f"{state['origin']} to {state['destination']}."
                ),
            }

        top_pois = state["top_pois"]

        # Enrich each POI with Wikipedia text + thumbnail
        if self._wikipedia_fetcher is not None:
            for sp in top_pois:
                self._wikipedia_fetcher.enrich(sp.poi)

        # If KnowledgeRAG is wired: run 3-stage GraphRAG pipeline
        if self._knowledge_rag is not None:
            preferences = state.get("preferences") or []
            route_coords = state["route_result"].route_coords if state.get("route_result") else []

            if self._poi_chunker is not None:
                pois = [sp.poi for sp in top_pois]
                self._poi_chunker.chunk_and_index(pois)

            poi_context = self._knowledge_rag.query(
                preferences=preferences,
                route_coords=route_coords,
            )
            # Fall back to plain context if KnowledgeRAG returned nothing
            if not poi_context:
                poi_context = self._build_poi_context(top_pois)
        else:
            # Legacy path: plain context (used when KnowledgeRAG not wired)
            if self._poi_indexer is not None:
                pois = [sp.poi for sp in top_pois]
                self._poi_indexer.index(pois)
            poi_context = self._build_poi_context(top_pois)

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
        if state.get("error"):
            narrative = self._fallback_chain.generate(
                reason=state.get("fallback_reason", state["error"]),
                query=state["query"],
            )
        else:
            route_result = state["route_result"]
            narrative = self._narrative_chain.generate(
                origin=state["origin"],
                destination=state["destination"],
                distance_km=route_result.length_km,
                drive_time_min=route_result.drive_time_min,
                top_pois=state.get("top_pois") or [],
                poi_context=state.get("poi_context"),
            )
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
