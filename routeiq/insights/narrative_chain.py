from __future__ import annotations
import re
from collections.abc import Iterator
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from routeiq.routing.scored_poi import ScoredPOI


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models (Qwen3, DeepSeek-R1, QwQ)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).lstrip()


def _stream_skip_think(tokens: Iterator[str]) -> Iterator[str]:
    """Filter a token stream, silently dropping everything inside <think>...</think>.

    Buffers tokens until </think> is found, then streams the remainder normally.
    If no <think> tag appears within the first 20 chars, passes through immediately.
    No-op for models that don't emit think blocks (Claude, OpenAI).
    """
    buf = ""
    for token in tokens:
        buf += token
        if "</think>" in buf:
            after = buf[buf.index("</think>") + len("</think>"):]
            if after:
                yield after
            yield from tokens
            return
        if "<think>" not in buf and len(buf) > 20:
            yield buf
            yield from tokens
            return
    if buf:
        yield _strip_think(buf)


class NarrativeChain:
    """Generates a scenic route narrative from route data and top POIs (Chain pattern)."""

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
        result = self._chain.invoke({
            "origin": origin,
            "destination": destination,
            "distance_km": f"{distance_km:.1f}",
            "drive_time_min": f"{drive_time_min:.0f}",
            "poi_context": poi_context if poi_context is not None else self._format_poi_context(top_pois),
        })
        return _strip_think(result)

    def stream(
        self,
        origin: str,
        destination: str,
        distance_km: float,
        drive_time_min: float,
        top_pois: list[ScoredPOI],
        *,
        poi_context: str | None = None,
    ) -> Iterator[str]:
        tokens = self._chain.stream({
            "origin": origin,
            "destination": destination,
            "distance_km": f"{distance_km:.1f}",
            "drive_time_min": f"{drive_time_min:.0f}",
            "poi_context": poi_context if poi_context is not None else self._format_poi_context(top_pois),
        })
        yield from _stream_skip_think(tokens)

    @staticmethod
    def _format_poi_context(top_pois: list[ScoredPOI]) -> str:
        if not top_pois:
            return "No scenic stops found along this route."
        return "\n".join(
            f"{sp.poi.name} ({sp.poi.category}) — {sp.detour_km:.1f} km detour, {sp.detour_min:.0f} min"
            for sp in top_pois
        )
