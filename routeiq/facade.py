from __future__ import annotations
from typing import Optional
from langchain_core.language_models import BaseLanguageModel
import chromadb

from routeiq.graph import GraphLoader, POIFinder, RouteKnowledgeGraph
from routeiq.routing import DetourScorer, POISelector
from routeiq.insights import QueryParser, NarrativeChain, FallbackChain
from routeiq.insights.prompts import QUERY_PARSER_PROMPT, NARRATIVE_PROMPT, FALLBACK_PROMPT
from routeiq.rag import WikipediaFetcher, POIIndexer, POIRetriever, POIChunker, KnowledgeRAG
from routeiq.pipeline import RoutePipeline


class RouteIQFacade:
    """Single entry point that wires all RouteIQ components and exposes run() (Facade pattern)."""

    def __init__(
        self,
        llm: BaseLanguageModel,
        *,
        graph_loader: Optional[GraphLoader] = None,
        poi_finder: Optional[POIFinder] = None,
        detour_scorer: Optional[DetourScorer] = None,
        poi_selector: Optional[POISelector] = None,
        wikipedia_fetcher: Optional[WikipediaFetcher] = None,
        poi_indexer: Optional[POIIndexer] = None,
        poi_retriever: Optional[POIRetriever] = None,
        poi_chunker: Optional[POIChunker] = None,
        knowledge_rag: Optional[KnowledgeRAG] = None,
        knowledge_graph: Optional[RouteKnowledgeGraph] = None,
        chroma_client: Optional[chromadb.ClientAPI] = None,
    ) -> None:
        _indexer = poi_indexer or POIIndexer(client=chroma_client)
        _kg = knowledge_graph or RouteKnowledgeGraph()
        _chunker_indexer = POIIndexer(client=chroma_client, collection_name="routeiq_chunks")
        _chunker = poi_chunker or POIChunker(_chunker_indexer)
        _krag = knowledge_rag or KnowledgeRAG(_chunker_indexer, _kg)
        self._pipeline = RoutePipeline(
            query_parser=QueryParser(QUERY_PARSER_PROMPT, llm),
            graph_loader=graph_loader or GraphLoader(),
            poi_finder=poi_finder or POIFinder(),
            detour_scorer=detour_scorer or DetourScorer(),
            poi_selector=poi_selector or POISelector(),
            narrative_chain=NarrativeChain(NARRATIVE_PROMPT, llm),
            fallback_chain=FallbackChain(FALLBACK_PROMPT, llm),
            wikipedia_fetcher=wikipedia_fetcher or WikipediaFetcher(),
            poi_indexer=_indexer,
            poi_retriever=poi_retriever or POIRetriever(_indexer),
            poi_chunker=_chunker,
            knowledge_rag=_krag,
        )

    def run(self, query: str, on_progress=None) -> dict:
        """Run the full pipeline for a natural language route query."""
        return self._pipeline.run(query, on_progress=on_progress)

    def generate_narrative(
        self,
        origin: str,
        destination: str,
        distance_km: float,
        drive_time_min: float,
        poi_context: str,
    ) -> str:
        """Generate a narrative from arbitrary POI context — used for vector baseline view."""
        return self._pipeline._narrative_chain.generate(
            origin=origin,
            destination=destination,
            distance_km=distance_km,
            drive_time_min=drive_time_min,
            top_pois=[],
            poi_context=poi_context,
        )
