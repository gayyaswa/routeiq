from __future__ import annotations
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from routeiq.routing.scored_poi import ScoredPOI


class NarrativeChain:
    """Generates a scenic route narrative from route data and top POIs using Claude (Chain pattern)."""

    def __init__(self, prompt: ChatPromptTemplate, llm: BaseLanguageModel) -> None:
        self._chain = prompt | llm | StrOutputParser()

    def generate(
        self,
        origin: str,
        destination: str,
        distance_km: float,
        drive_time_min: float,
        top_pois: list[ScoredPOI],
        *,
        poi_context: str | None = None,
    ) -> str:
        return self._chain.invoke({
            "origin": origin,
            "destination": destination,
            "distance_km": f"{distance_km:.1f}",
            "drive_time_min": f"{drive_time_min:.0f}",
            "poi_context": poi_context if poi_context is not None else self._format_poi_context(top_pois),
        })

    @staticmethod
    def _format_poi_context(top_pois: list[ScoredPOI]) -> str:
        if not top_pois:
            return "No scenic stops found along this route."
        return "\n".join(
            f"{sp.poi.name} ({sp.poi.category}) — {sp.detour_km:.1f} km detour, {sp.detour_min:.0f} min"
            for sp in top_pois
        )
